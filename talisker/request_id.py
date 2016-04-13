from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from functools import wraps
import uuid

from .request_context import set_request_context, request_context
from .logs import set_logging_context


def generate_request_id():
    return str(uuid.uuid4()).encode('utf8')


def get_request_id():
    try:
        return request_context.request_id
    except AttributeError:
        return ""


def set_id(id):
    """Sets id in both general request context, and specific logging dict"""
    set_request_context(request_id=id)
    set_logging_context(request_id=id)


def set_request_id(get_id):
    """Decorator to set a thread local request id for function.

    Takes a function that will return the request id from the function params,
    so you can configure it. Cleans up on the way out.
    """
    def wrapper(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            id = get_id(*args, **kwargs)
            set_id(id)
            return func(*args, **kwargs)
        return decorator
    return wrapper


class RequestIdMiddleware(object):
    """WSGI middleware to set the request id."""

    def __init__(self, app, header='X-Request-Id'):
        self.app = app
        self.header = header.encode('utf8')
        self.wsgi_header = 'HTTP_' + header.upper().replace('-', '_')
        self.wsgi_header = self.wsgi_header.encode('utf8')

    def __call__(self, environ, start_response):
        if self.wsgi_header not in environ:
            environ[self.wsgi_header] = generate_request_id()
        id = environ[self.wsgi_header]
        set_id(id)
        environ[b'REQUEST_ID'] = id
        return self.app(environ, start_response)
