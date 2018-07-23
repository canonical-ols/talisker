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

from functools import wraps
import uuid
from contextlib import contextmanager

from werkzeug.datastructures import Headers

from talisker.logs import logging_context


__all__ = [
    'HEADER',
    'get',
    'push',
    'context',
    'decorator',
]

HEADER = 'X-Request-Id'


def generate():
    return str(uuid.uuid4())


def get():
    return logging_context.get('request_id')


def push(id):
    return logging_context.push(request_id=id)


# b/w compat alias
set = push


# provide a nicer ctx manager api
@contextmanager
def context(id):
    with logging_context(request_id=id):
        yield


def decorator(id_func):
    """Decorator to set a thread local request id for function.

    Takes a function that will return the request id from the function params,
    so you can configure it. Cleans up on the way out.
    """
    def wrapper(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            id = id_func(*args, **kwargs)

            if id:
                with context(id):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return decorator
    return wrapper


class RequestIdMiddleware(object):
    """WSGI middleware to set the request id."""

    def __init__(self, app, header=HEADER):
        self.app = app
        self.header = header
        self.wsgi_header = 'HTTP_' + header.upper().replace('-', '_')

    def __call__(self, environ, start_response):
        if self.wsgi_header not in environ:
            environ[self.wsgi_header] = generate()
        rid = environ[self.wsgi_header]
        # don't worry about popping, as wsgi context is cleared
        logging_context.push(request_id=rid)
        environ['REQUEST_ID'] = rid

        def add_id_header(status, response_headers, exc_info=None):
            headers = Headers(response_headers)
            headers.set(self.header, rid)
            start_response(status, headers, exc_info)

        return self.app(environ, add_id_header)
