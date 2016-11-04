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

from raven import Client
from raven.middleware import Sentry
from raven.breadcrumbs import _record_log_breadcrumb as record_log_breadcrumb

from talisker import revision

__all__ = [
    'get_client'
    'record_log_breadcrumb',
]

_client = None

default_processors = [
    'raven.processors.RemovePostDataProcessor',
    'raven.processors.SanitizePasswordsProcessor',
    'raven.processors.RemoveStackLocalsProcessor',
]


def get_client(dsn=None):
    global _client

    if _client is None:
        kwargs = {
            'dsn': dsn,
            'processors': default_processors,
            'release': revision.get(),
            'install_logging_hook': False,
            'hook_libraries': [],
            # TODO: environment, JUJU_ENV?
            # TODO: name, JUJU_UNIT?
        }
        _client = Client(**kwargs)

    return _client


def get_middleware(app):
    return Sentry(app, get_client())
