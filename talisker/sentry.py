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

from talisker import revision
from talisker.util import module_cache, module_dict, parse_url

record_log_breadcrumb = raven.breadcrumbs._record_log_breadcrumb


__all__ = [
    'get_client'
    'record_log_breadcrumb',
]

_client = None

default_processors = set([
    'raven.processors.RemovePostDataProcessor',
    'raven.processors.SanitizePasswordsProcessor',
    'raven.processors.RemoveStackLocalsProcessor',
])

sentry_globals = module_dict()


def register_client_update(update_func):
    sentry_globals.setdefault('updates', []).append(update_func)
    return update_func


def ensure_talisker_config(kwargs):
    # ensure default processors
    processors = kwargs.get('processors')
    if not processors:
        processors = set([])
    kwargs['processors'] = list(default_processors | processors)

    # override it or it interferes with talisker logging
    if kwargs.get('install_logging_hook'):
        logging.getLogger(__name__).info(
            'ignoring install_logging_hook=True in sentry config '
            '- talisker manages this')
    kwargs['install_logging_hook'] = False

    kwargs.setdefault('release', revision.get())
    # don't hook libraries by default
    kwargs.setdefault('hook_libraries', [])

    # set from the environment
    kwargs.setdefault('environment', os.environ.get('TALISKER_ENV'))
    # if not set, will default to hostname
    kwargs.setdefault('name', os.environ.get('TALISKER_UNIT'))
    kwargs.setdefault('site', os.environ.get('TALISKER_DOMAIN'))


@module_cache
def get_client(**kwargs):
    from_env = False
    if 'dsn' not in kwargs:
        kwargs['dsn'] = os.environ.get('SENTRY_DSN')
        from_env = True

    ensure_talisker_config(kwargs)
    client = raven.Client(**kwargs)

    # log useful information
    if client.is_enabled():
        # base_url shouldn't have secrets in, but just in case, clean it
        url = parse_url(client.remote.base_url)
        host = url.scheme + '://' + url.hostname
        msg = 'configured raven'
        if from_env:
            msg += ' from SENTRY_DSN environment'
        logging.getLogger(__name__).info(msg, extra={'host': host})

    return client


def set_client(**kwargs):
    client = get_client.update(**kwargs)
    for update_func in sentry_globals.get('updates', []):
        update_func(client)
    return client


def get_middleware(app):
    client = get_client()
    middleware = raven.middleware.Sentry(app, client=client)

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
