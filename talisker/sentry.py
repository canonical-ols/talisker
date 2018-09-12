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
import os
import time

import raven
import raven.middleware
import raven.handlers.logging
import raven.breadcrumbs

import talisker.revision
import talisker.request_id
import talisker.logs
from talisker.util import (
    module_cache,
    module_dict,
    parse_url,
    sanitize_url,
)

__all__ = [
    'get_client',
    'configure_client',
    'set_client',
    'register_client_update',
]

default_processors = set([
    'raven.processors.RemovePostDataProcessor',
    'raven.processors.SanitizePasswordsProcessor',
    'raven.processors.RemoveStackLocalsProcessor',
])

sentry_globals = module_dict()

# sql queries and http requests are recorded as explicit breadcrumbs as well as
# logged, so ignore the log breadcrumb
raven.breadcrumbs.ignore_logger('talisker.slowqueries')
raven.breadcrumbs.ignore_logger('talisker.requests')


def register_client_update(update_func):
    sentry_globals.setdefault('updates', []).append(update_func)
    return update_func


def update_client_references(client):
    for update_func in sentry_globals.get('updates', []):
        update_func(client)


def ensure_talisker_config(kwargs):
    # ensure default processors
    # this is provided as a list from settings, but we need a set
    # to ensure we don't duplicate
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
        kwargs['release'] = talisker.revision.get()
    # don't hook libraries by default
    if kwargs.get('hook_libraries') is None:
        kwargs['hook_libraries'] = []

    tags = kwargs.get('tags', {})

    # set from the environment
    unit = os.environ.get('TALISKER_UNIT')
    env = os.environ.get('TALISKER_ENV')
    domain = os.environ.get('TALISKER_DOMAIN')
    if unit is not None:
        tags['unit'] = unit
    if env is not None:
        tags['environment'] = env
    if domain is not None:
        tags['domain'] = domain
    kwargs['tags'] = tags

    from_env = False
    dsn = kwargs.get('dsn', None)
    if not dsn:
        kwargs['dsn'] = os.environ.get('SENTRY_DSN')
        from_env = True

    return from_env


def log_client(client, from_env=False):
    """Safely log client creation at INFO level."""
    if not client.is_enabled():
        # raven already logs a *disabled* client at INFO level
        return

    # base_url shouldn't have secrets in, but just in case, clean it
    public_dsn = client.remote.get_public_dsn()
    scheme = parse_url(client.remote.base_url).scheme
    url = scheme + ':' + public_dsn
    clean_url = sanitize_url(url)
    msg = 'configured raven'
    extra = {'dsn': clean_url}
    if from_env:
        msg += ' from SENTRY_DSN environment'
        extra['from_env'] = True
    logging.getLogger(__name__).info(msg, extra=extra)


def add_talisker_context(data):
    rid = talisker.request_id.get()
    if rid:
        data['tags']['request_id'] = rid
    data['extra'].update(talisker.logs.logging_context.flat)

    breadcrumbs = data.get('breadcrumbs', {})
    sql_crumbs = []

    for crumb in breadcrumbs.get('values', []):
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

    def __init__(self, *args, **kwargs):
        from_env = ensure_talisker_config(kwargs)
        super().__init__(*args, **kwargs)
        log_client(self, from_env)
        set_client(self)

    def build_msg(self, event_type, *args, **kwargs):
        data = super().build_msg(event_type, *args, **kwargs)
        add_talisker_context(data)
        return data


class TaliskerSentryMiddleware(raven.middleware.Sentry):

    def __call__(self, environ, start_response):
        start_time = time.time()
        environ['start_time'] = start_time
        self.client.extra_context({'start_time': start_time})
        soft_start_timeout = talisker.get_config()['soft_request_timeout']
        if soft_start_timeout >= 0:

            def soft_timeout_start_response(status, headers, exc_info=None):
                response = start_response(status, headers, exc_info=exc_info)
                duration = (time.time() - environ['start_time']) * 1000
                if (soft_start_timeout is not None and
                        duration > soft_start_timeout):
                    self.client.captureMessage(
                        'Start_response over timeout: {}'
                        .format(soft_start_timeout),
                        level='warning'
                    )
                return response
            return super().__call__(environ, soft_timeout_start_response)
        else:
            return super().__call__(environ, start_response)


@module_cache
def get_client(**kwargs):
    return TaliskerSentryClient(**kwargs)


def configure_client(**kwargs):
    client = get_client.update(**kwargs)
    update_client_references(client)
    return client


def set_client(client):
    get_client.raw_update(client)
    update_client_references(client)
    return client


def get_middleware(app):
    client = get_client()
    middleware = TaliskerSentryMiddleware(app, client=client)

    @register_client_update
    def middleware_update(client):
        middleware.client = client

    return middleware


@module_cache
def get_log_handler():
    client = get_client()
    handler = raven.handlers.logging.SentryHandler(client=client)

    @register_client_update
    def handler_update(client):
        handler.client = client

    return handler
