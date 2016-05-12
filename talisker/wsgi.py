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


def set_environ(app, **kwargs):
    def middleware(environ, start_response):
        for key, value in kwargs.items():
            environ[key] = value
        return app(environ, start_response)
    return middleware


def set_headers(app, headers):
    def middleware(environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            for header, value in headers.items():
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
    wrapped = set_headers(wrapped, {'X-Revision': revision.get()})
    wrapped = endpoints.StandardEndpointMiddleware(wrapped)
    # set some standard environ items
    wrapped = set_environ(
        wrapped,
        statsd=statsd.get_client(),
        requests=requests.default_session(),
    )
    # add request id info to thread locals
    wrapped = request_id.RequestIdMiddleware(wrapped)
    # clean up request context on the way out
    wrapped = request_context.cleanup_middleware(wrapped)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
