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
