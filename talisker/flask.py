from raven.contrib.flask import Sentry
import talisker.raven

def sentry(app):
    return Sentry(app,
                  client=talisker.raven.get_client(),
                  logging=False,
                  wrap_wsgi=None,
                  register_signal=False)
