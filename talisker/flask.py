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


def _setup(app):
    # silence flasks handlers log handlers.
    app.config['LOGGER_HANDLER_POLICY'] = 'never'
    sentry(app)


def register(app):
    """Register a flask app with talisker."""
    _setup(app)
    # hack to actually remove flasks log handlers
    app._logger = logging.getLogger(app.logger_name)


class TaliskerApp(flask.Flask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _setup(self)

    # flasks default logger is not needed with talisker
    @property
    def logger(self):
        return logging.getLogger(self.logger_name)
