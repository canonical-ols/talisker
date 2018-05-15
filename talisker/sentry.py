# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import logging
import os

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

    # set from the environment
    if kwargs.get('environment') is None:
        kwargs['environment'] = os.environ.get('TALISKER_ENV')
    # if not set, will default to hostname
    if kwargs.get('name') is None:
        kwargs['name'] = os.environ.get('TALISKER_UNIT')
    if kwargs.get('site') is None:
        kwargs['site'] = os.environ.get('TALISKER_DOMAIN')

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


def add_talisker_context(tags, extra):
    if tags is None:
        tags = {}
    if extra is None:
        extra = {}
    rid = talisker.request_id.get()
    if rid:
        tags['request_id'] = rid
    extra.update(talisker.logs.logging_context.flat)
    return tags, extra


class TaliskerSentryClient(raven.Client):

    def __init__(self, *args, **kwargs):
        from_env = ensure_talisker_config(kwargs)
        super().__init__(*args, **kwargs)
        log_client(self, from_env)
        set_client(self)

    def capture(self, event_type, tags=None, extra=None, **kwargs):
        tags, extra = add_talisker_context(tags, extra)
        super().capture(event_type, tags=tags, extra=extra, **kwargs)


class TaliskerSentryMiddleware(raven.middleware.Sentry):

    def __call__(self, environ, start_response):
        # we clear the sentry context before the request starts, in order to
        # avoid picking up gunicorn log messages from previous requests
        self.client.context.clear()
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
