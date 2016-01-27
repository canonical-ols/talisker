from talisker.request_id import RequestIdMiddleware
from talisker.context import manager


def wsgi_wrap(app):
    wrapped = app
    # add request id info to thread locals
    wrapped = RequestIdMiddleware(wrapped)
    # clean up thread locals on the way out
    wrapped = manager.make_middleware(wrapped)
    return wrapped
