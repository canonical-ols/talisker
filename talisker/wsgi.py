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

from . import request_id
from . import request_context
from . import endpoints
from . import statsd
from . import requests
from . import revision


__all__ = [
    'set_environ',
    'set_headers',
    'wrap'
    ]

def set_environ(app, **kwargs):
    def middleware(environ, start_response):
        for key, value in kwargs.items():
            environ[key] = value
        return app(environ, start_response)
    return middleware


def set_headers(app, add_headers):
    def middleware(environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            for header, value in add_headers.items():
                headers.append((header, value))
            return start_response(status, headers, exc_info)
        return app(environ, custom_start_response)
    return middleware


def wrap(app):
    if getattr(app, '_talisker_wrapped', False):
        return app

    wrapped = app
    # added in reverse order
    # expose some standard endpoint
    wrapped = endpoints.StandardEndpointMiddleware(wrapped)
    # set some standard environ items
    wrapped = set_environ(
        wrapped,
        statsd=statsd.get_client(),
        requests=requests.get_session(),
    )
    # add request id info to thread locals
    wrapped = request_id.RequestIdMiddleware(wrapped)
    wrapped = set_headers(wrapped, {'X-VCS-Revision': revision.header()})
    # clean up request context on the way out
    wrapped = request_context.cleanup_middleware(wrapped)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
