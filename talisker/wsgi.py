#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from werkzeug.datastructures import Headers

import talisker.request_id
import talisker.context
import talisker.endpoints
import talisker.statsd
import talisker.requests
import talisker.revision
import talisker.sentry


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
    """Adds headers to response, overwriting any existing values."""
    def middleware(environ, start_response):
        def custom_start_response(status, response_headers, exc_info=None):
            headers = Headers(response_headers)
            for header, value in add_headers.items():
                headers.set(header, value)
            return start_response(status, headers, exc_info)
        return app(environ, custom_start_response)
    return middleware


def wrap(app):
    if getattr(app, '_talisker_wrapped', False):
        return app

    wrapped = app
    # added in reverse order
    wrapped = set_headers(
        wrapped, {'X-VCS-Revision': talisker.revision.header()})
    # expose some standard endpoint
    wrapped = talisker.endpoints.StandardEndpointMiddleware(wrapped)
    # set some standard environ items
    wrapped = set_environ(
        wrapped,
        statsd=talisker.statsd.get_client(),
        requests=talisker.requests.get_session(),
    )
    # add request id info to thread locals
    wrapped = talisker.request_id.RequestIdMiddleware(wrapped)
    wrapped = talisker.sentry.get_middleware(wrapped)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
