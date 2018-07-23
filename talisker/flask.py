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

import logging

import flask
import raven.contrib.flask
import talisker.sentry


__all__ = [
    'sentry',
    'register',
    'TaliskerApp',
]


class FlaskSentry(raven.contrib.flask.Sentry):

    def after_request(self, sender, response, *args, **kwargs):
        # override after_request to not clear context and transaction
        if self.last_event_id:
            response.headers['X-Sentry-ID'] = self.last_event_id
        return response


def sentry(app, dsn=None, transport=None, **kwargs):
    """Enable sentry for a flask app, talisker style."""
    # transport is just to support testing, not used in prod
    kwargs['logging'] = False
    kwargs.pop('client', None)
    kwargs['client_cls'] = talisker.sentry.TaliskerSentryClient
    kwargs['wrap_wsgi'] = False
    logging.getLogger(__name__).info('updating raven config from flask app')
    sentry = FlaskSentry(app, **kwargs)
    # tag sentry reports with the flask app
    sentry.client.tags['flask_app'] = app.name
    return sentry


def add_view_name(response):

    name = flask.request.endpoint

    if name is not None and flask.current_app:
        try:
            if name in flask.current_app.view_functions:
                module = flask.current_app.view_functions[name].__module__
                name = module + '.' + name
        except Exception:
            pass

    if name is None:
        # this is not a critical error, so just debug log it.
        logging.getLogger(__name__).debug('no flask view for {}'.format(
            flask.request.path
        ))
    else:
        response.headers['X-View-Name'] = name

    return response


def setup(app):
    sentry(app)
    app.after_request(add_view_name)


def register(app):
    """Register a flask app with talisker."""
    # override flask default app logger set up
    if hasattr(app, 'logger_name'):
        app.config['LOGGER_HANDLER_POLICY'] = 'never'
        app._logger = logging.getLogger(app.logger_name)
    else:
        # we can just set the logger directly
        app.logger = logging.getLogger('flask.app')
    setup(app)


class TaliskerApp(flask.Flask):

    def __init__(self, app, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        if hasattr(self, 'logger_name'):
            self.config['LOGGER_HANDLER_POLICY'] = 'never'
            self._logger = logging.getLogger(self.logger_name)
        else:
            self._logger = logging.getLogger('flask.app')
        setup(self)

    @property
    def logger(self):
        return self._logger
