#-*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from functools import wraps
import uuid

from .context import set_context, context
from .logs import set_logging_context


def generate_request_id():
    return str(uuid.uuid4())


def get_request_id():
    try:
        return context.request_id
    except AttributeError:
        return ""


def set_request_id(get_id):
    """Decorator to set a thread local request id for function.

    Takes a function that will return the request id from the function params,
    so you can configure it. Cleans up on the way out.
    """
    def wrapper(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            id = get_id(*args, **kwargs)
            set_context(request_id=id)
            set_logging_context(request_id=id)
            return func(*args, **kwargs)
        return decorator
    return wrapper


class RequestIdMiddleware(object):
    """WSGI middleware to set the request id."""

    def __init__(self, app, header='X-Request-Id'):
        self.app = app
        self.header = header
        self.wsgi_header = 'HTTP_' + header.upper().replace('-', '_')

    def __call__(self, environ, start_response):
        if self.wsgi_header not in environ:
            environ[self.wsgi_header] = generate_request_id()

        id = environ[self.wsgi_header]
        environ['REQUEST_ID'] = id
        set_context(request_id=id)
        set_logging_context(request_id=id)
        return self.app(environ, start_response)
