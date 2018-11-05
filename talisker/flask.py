#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
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
    _client_set = False

    @property
    def client(self):
        """Return None if not yet set, so we do actually create the client."""
        if self._client_set:
            return talisker.sentry.get_client()
        else:
            return None

    @client.setter
    def client(self, client):
        """We let the flask extension create the sentry client."""
        if client is not None:
            self._client_set = True
            talisker.sentry.set_client(client)

    def after_request(self, sender, response, *args, **kwargs):
        # override after_request to not clear context and transaction
        if self.last_event_id:
            response.headers['X-Sentry-ID'] = self.last_event_id
        return response


def sentry(app, dsn=None, transport=None, **kwargs):
    """Enable sentry for a flask app, talisker style."""
    # transport is just to support testing, not used in prod
    kwargs['logging'] = False
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
