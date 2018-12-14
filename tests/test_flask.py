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

import pytest

try:
    from flask import Flask
except ImportError:
    pytest.skip('skipping flask tests', allow_module_level=True)

import talisker.flask

from talisker.testing import (
    DummySentryTransport,
    TEST_SENTRY_DSN,
    get_sentry_messages,
)


class IgnoredException(Exception):
    pass


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config['SENTRY_TRANSPORT'] = DummySentryTransport
    app.config['SENTRY_DSN'] = TEST_SENTRY_DSN

    @app.route('/')
    def error():
        raise Exception('app exception')

    @app.route('/ignored')
    def ignored():
        raise IgnoredException('test exception')

    return app


def get_url(the_app, *args, **kwargs):
    app_client = the_app.test_client()
    with the_app.app_context():
        return app_client.get(*args, **kwargs)


def test_flask_sentry_sends_message(flask_app):
    sentry = talisker.flask.sentry(flask_app)
    response = get_url(flask_app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert len(msgs) == 1
    msg = msgs[0]
    if 'culprit' in msg:
        assert msg['culprit'] == '/'
    else:
        assert msg['transaction'] == '/'


def test_flask_sentry_default_include_paths(flask_app):
    sentry = talisker.flask.sentry(flask_app)
    assert sentry.client.include_paths == set(['tests.test_flask'])


def test_flask_sentry_app_config_ignore_exc(flask_app, monkeypatch, context):
    monkeypatch.setitem(flask_app.config, 'SENTRY_CONFIG', {
        'ignore_exceptions': ['IgnoredException']
    })
    sentry = talisker.flask.sentry(flask_app)

    assert 'IgnoredException' in sentry.client.ignore_exceptions

    response = get_url(flask_app, '/ignored')

    assert response.status_code == 500
    assert len(get_sentry_messages(sentry.client)) == 0


def test_flask_sentry_uses_app_config_to_set_name(flask_app, monkeypatch):
    monkeypatch.setitem(flask_app.config, 'SENTRY_NAME', 'SomeName')
    sentry = talisker.flask.sentry(flask_app)
    assert sentry.client.name == 'SomeName'

    response = get_url(flask_app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg['server_name'] == 'SomeName'


def test_flask_sentry_app_tag(flask_app):
    sentry = talisker.flask.sentry(flask_app)
    response = get_url(flask_app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert msgs[0]['tags']['flask_app'] == flask_app.name


def test_flask_sentry_not_clear_afer_request(monkeypatch):
    app = Flask(__name__)

    @app.route('/')
    def index():
        return 'ok'

    sentry = talisker.flask.sentry(app)
    calls = []
    monkeypatch.setattr(sentry.client.context, 'clear',
                        lambda: calls.append(1))
    get_url(app, '/')
    assert len(calls) == 0
    assert isinstance(sentry, talisker.flask.FlaskSentry)


def test_talisker_flask_app():
    app = talisker.flask.TaliskerApp(__name__)
    logname = getattr(app, 'logger_name', 'flask.app')

    assert 'sentry' in app.extensions
    assert app.logger is logging.getLogger(logname)

    if 'LOGGER_HANDLER_POLICY' in app.config:
        assert app.config['LOGGER_HANDLER_POLICY'] == 'never'


def test_register_app():
    app = Flask(__name__)
    talisker.flask.register(app)

    logname = getattr(app, 'logger_name', 'flask.app')
    assert 'sentry' in app.extensions
    assert app.logger is logging.getLogger(logname)
    if 'LOGGER_HANDLER_POLICY' in app.config:
        assert app.config['LOGGER_HANDLER_POLICY'] == 'never'


def test_flask_view_name_header():
    app = Flask(__name__)

    @app.route('/')
    def index():
        return 'ok'

    talisker.flask.register(app)
    response = get_url(app, '/')
    assert response.headers['X-View-Name'] == 'tests.test_flask.index'


def test_flask_view_name_header_no_view(context):
    app = Flask(__name__)

    @app.route('/')
    def index():
        return 'ok'

    talisker.flask.register(app)
    context.logs[:] = []
    response = get_url(app, '/notexist')
    assert 'X-View-Name' not in response.headers
    context.assert_log(msg="no flask view for /notexist")


def test_flask_extension_updates_sentry_client():
    orig_client = talisker.sentry.get_client()
    app = Flask(__name__)
    ext = talisker.flask.sentry(app)
    assert ext.client is not orig_client
    assert talisker.sentry.get_client() is not orig_client
