from talisker.request_id import RequestIdMiddleware
from talisker.context import manager


def wsgi_wrap(app):
    if not getattr(app, '_talisker_wrapped', False):
        wrapped = app
        # add request id info to thread locals
        wrapped = RequestIdMiddleware(wrapped)
        # clean up thread locals on the way out
        wrapped = manager.make_middleware(wrapped)
        wrapped._talisker_wrapped = True
        wrapped._talisker_original_app = app
        return wrapped
    else:
        return app
