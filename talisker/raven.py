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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import logging
import os

from raven import Client
from raven.middleware import Sentry
from raven.breadcrumbs import _record_log_breadcrumb

from talisker import revision
from talisker.util import module_cache

record_log_breadcrumb = _record_log_breadcrumb


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
    ensure_talisker_config(kwargs)
    return Client(**kwargs)


def get_middleware(wsgi_app):
    return Sentry(wsgi_app, get_client())
