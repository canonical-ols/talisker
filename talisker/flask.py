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

import logging

import flask
import raven.contrib.flask
import talisker.sentry


__all__ = [
    'sentry',
    'register',
    'TaliskerApp',
]


def sentry(app, dsn=None, transport=None, **kwargs):
    """Enable sentry for a flask app, talisker style."""
    # transport is just to support testing, not used in prod
    kwargs['logging'] = False
    kwargs.pop('client', None)
    kwargs['client_cls'] = talisker.sentry.TaliskerSentryClient
    kwargs['wrap_wsgi'] = False
    logging.getLogger(__name__).info('updating raven config from flask app')
    sentry = raven.contrib.flask.Sentry(app, **kwargs)
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
