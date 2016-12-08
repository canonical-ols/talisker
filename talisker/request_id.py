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
from contextlib import contextmanager
import uuid

from .request_context import request_context
from .logs import set_logging_context


__all__ = [
    'HEADER',
    'get',
    'set',
    'context',
    'decorator',
]

HEADER = 'X-Request-Id'


def generate():
    return str(uuid.uuid4())


def get():
    try:
        return request_context.request_id
    except AttributeError:
        return None


def set(id):
    """Sets id in both general request context, and specific logging dict"""
    if id is None:
        if hasattr(request_context, 'request_id'):
            del request_context.request_id
        if hasattr(request_context, 'extra'):
            request_context.extra.pop('request_id', None)
    else:
        request_context.request_id = id
        set_logging_context(request_id=id)


@contextmanager
def context(id):
    old_id = get()
    set(id)
    yield
    set(old_id)


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
        id = environ[self.wsgi_header]
        set(id)
        environ['REQUEST_ID'] = id

        def add_id_header(status, headers, exc_info=None):
            headers.append((self.header, id))
            start_response(status, headers, exc_info)

        return self.app(environ, add_id_header)
