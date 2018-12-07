#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from collections import OrderedDict
import logging
import re
import time

import raven
import raven.middleware
import raven.handlers.logging
import raven.breadcrumbs

import talisker
import talisker.request_id
import talisker.logs
from talisker.util import (
    get_rounded_ms,
    module_cache,
    parse_url,
    sanitize_url,
)

__all__ = [
    'get_client',
    'configure_client',
    'set_client',
]

default_processors = set([
    'raven.processors.RemovePostDataProcessor',
    'raven.processors.SanitizePasswordsProcessor',
    'raven.processors.RemoveStackLocalsProcessor',
])

# sql queries and http requests are recorded as explicit breadcrumbs as well as
# logged, so ignore the log breadcrumb
raven.breadcrumbs.ignore_logger('talisker.slowqueries')
raven.breadcrumbs.ignore_logger('talisker.requests')


def clear():
    """Clear any sentry state."""
    raven.context._active_contexts.__dict__.clear()


def ensure_talisker_config(kwargs):
    # ensure default processors
    # this is provided as a list from settings, but we need a set
    # to ensure we don't duplicate
    config = talisker.get_config()
    processors = set(kwargs.get('processors') or [])
    kwargs['processors'] = list(default_processors | processors)

    # override it or it interferes with talisker logging
    if kwargs.get('install_logging_hook'):
        logging.getLogger(__name__).info(
            'ignoring install_logging_hook=True in sentry config '
            '- talisker manages this')
    kwargs['install_logging_hook'] = False

    # flask integration explictly sets options as None
    if kwargs.get('release') is None:
        kwargs['release'] = talisker.get_config().revision_id
    # don't hook libraries by default
    if kwargs.get('hook_libraries') is None:
        kwargs['hook_libraries'] = []

    tags = kwargs.get('tags', {})

    # set from the environment
    if config.unit is not None:
        tags['unit'] = config.unit
    if config.environment is not None:
        tags['environment'] = config.environment
    if config.domain is not None:
        tags['domain'] = config.domain
    kwargs['tags'] = tags

    dsn = kwargs.get('dsn', None)
    if not dsn:
        kwargs['dsn'] = config.sentry_dsn


def log_client(client):
    """Safely log client creation at INFO level."""
    if not client.is_enabled():
        # raven already logs a *disabled* client at INFO level
        return

    # base_url shouldn't have secrets in, but just in case, clean it
    public_dsn = client.remote.get_public_dsn()
    scheme = parse_url(client.remote.base_url).scheme
    url = scheme + ':' + public_dsn
    clean_url = sanitize_url(url)
    msg = 'configured raven DSN'
    extra = {'dsn': clean_url}
    config = talisker.get_config()
    env_cfg = config.raw.get('SENTRY_DSN')
    if env_cfg:
        # make a full url look like a public dsn
        clean_env = sanitize_url(re.sub(r'://(.*):.*@', r'://\1@', env_cfg))
        if clean_env == clean_url:
            msg += ' from SENTRY_DSN config'
            extra['from_env'] = True
        else:
            msg += ' overriding SENTRY_DSN config'
            extra['SENTRY_DSN'] = clean_env
    logging.getLogger(__name__).info(msg, extra=extra)


def add_talisker_context(data):
    rid = talisker.request_id.get()
    if rid:
        data['tags']['request_id'] = rid
    data['extra'].update(talisker.logs.logging_context.flat)

    user = data.get('user')
    if user:
        user.pop('email', None)
        user.pop('username', None)

    breadcrumbs = data.get('breadcrumbs', {}).get('values', [])
    start_time = data['extra'].get('start_time')
    sql_crumbs = []

    for crumb in breadcrumbs:
        if start_time:
            crumb['data']['start'] = get_rounded_ms(
                start_time, crumb['timestamp']
            )
        if crumb['category'] == 'sql':
            sql_crumbs.append(crumb)

    if sql_crumbs:
        summary = sql_summary(sql_crumbs, data['extra'].get('start_time'))
        data['extra']['sql summary'] = summary


def sql_summary(sql_crumbs, start_time):

    def duration(crumb):
        return float(crumb['data'].get('duration', 0))

    sql_crumbs.sort(key=duration, reverse=True)
    sql_time = sum(duration(c) for c in sql_crumbs)
    sql_summary = OrderedDict()
    sql_summary['sql_count'] = len(sql_crumbs)
    sql_summary['sql_time'] = sql_time

    if start_time is not None:
        request_time = (time.time() - start_time) * 1000
        sql_summary['non_sql_time'] = request_time - sql_time
        sql_summary['total_time'] = request_time

    sql_summary['slowest queries'] = [
        OrderedDict([
            ('duration', c['data']['duration']),
            ('query', c['data']['query'])]
        )
        for c in sql_crumbs[:5]
    ]

    return sql_summary


class TaliskerSentryClient(raven.Client):

    @property
    def logger(self):
        return logging.getLogger(__name__)

    @logger.setter
    def logger(self, value):
        """Ignore raven.clients logger"""

    def __init__(self, *args, **kwargs):
        ensure_talisker_config(kwargs)
        super().__init__(*args, **kwargs)

    def build_msg(self, event_type, *args, **kwargs):
        data = super().build_msg(event_type, *args, **kwargs)
        add_talisker_context(data)
        return data

    def set_dsn(self, dsn=None, transport=None):
        super().set_dsn(dsn, transport)
        log_client(self)


class ProxyClientMixin(object):
    """Mixin that overrides self.client to be a property.

    This allows reuse of the various raven handlers, which use a client
    attribute, but have that attribute actually get the global client."""

    @property
    def client(self):
        return get_client()

    @client.setter
    def client(self, client):
        """Ignore, as we should be using the global client."""
        pass


class TaliskerSentryLoggingHandler(
        ProxyClientMixin, raven.handlers.logging.SentryHandler):

    def __init__(self):
        # explicitly pass client, so that the Handler doesn't try create it's
        # own client
        super().__init__(client=get_client())


class TaliskerSentryMiddleware(ProxyClientMixin, raven.middleware.Sentry):

    def __init__(self, application):
        # explicitly pass client, so that the Middleware doesn't try create
        # it's own client
        super().__init__(application, get_client())

    def __call__(self, environ, start_response):
        start_time = time.time()
        environ['start_time'] = start_time
        self.client.extra_context({'start_time': start_time})
        soft_start_timeout = talisker.get_config().soft_request_timeout
        if soft_start_timeout >= 0:

            def soft_timeout_start_response(status, headers, exc_info=None):
                response = start_response(status, headers, exc_info=exc_info)
                duration = (time.time() - environ['start_time']) * 1000
                if (soft_start_timeout is not None
                        and duration > soft_start_timeout):
                    self.client.captureMessage(
                        'Start_response over timeout: {}'
                        .format(soft_start_timeout),
                        level='warning'
                    )
                return response
            return super().__call__(environ, soft_timeout_start_response)
        else:
            return super().__call__(environ, start_response)


_client = None


def get_client(**kwargs):
    global _client
    if _client is None:
        _client = TaliskerSentryClient(**kwargs)
    return _client


def configure_client(**kwargs):
    global _client
    _client = TaliskerSentryClient(**kwargs)
    return _client


def set_client(client):
    global _client
    _client = client
    return _client


# module global so we can add filters to it for celery
@module_cache
def get_log_handler():
    return TaliskerSentryLoggingHandler()
