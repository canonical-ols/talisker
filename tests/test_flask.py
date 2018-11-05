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

from flask import Flask

import talisker.flask

from talisker.testing import (
    DummySentryTransport,
    TEST_SENTRY_DSN,
    get_sentry_messages,
)


class IgnoredException(Exception):
    pass


app = Flask(__name__)
app.config['SENTRY_TRANSPORT'] = DummySentryTransport
app.config['SENTRY_DSN'] = TEST_SENTRY_DSN


@app.route('/')
def error():
    raise Exception('app exception')


@app.route('/ignored')
def ignored():
    raise IgnoredException('test exception')


def get_url(the_app, *args, **kwargs):
    app_client = the_app.test_client()
    with the_app.app_context():
        return app_client.get(*args, **kwargs)


def test_flask_sentry_sends_message():
    sentry = talisker.flask.sentry(app)
    response = get_url(app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert len(msgs) == 1
    msg = msgs[0]
    if 'culprit' in msg:
        assert msg['culprit'] == '/'
    else:
        assert msg['transaction'] == '/'


def test_flask_sentry_default_include_paths():
    sentry = talisker.flask.sentry(app)
    assert sentry.client.include_paths == set(['tests.test_flask'])


def test_flask_sentry_uses_app_config_to_ingnore_exc(monkeypatch, context):
    monkeypatch.setitem(app.config, 'SENTRY_CONFIG', {
        'ignore_exceptions': ['IgnoredException']
    })
    sentry = talisker.flask.sentry(app)

    assert 'IgnoredException' in sentry.client.ignore_exceptions

    response = get_url(app, '/ignored')

    assert response.status_code == 500
    assert len(get_sentry_messages(sentry.client)) == 0


def test_flask_sentry_uses_app_config_to_set_name(monkeypatch):
    monkeypatch.setitem(app.config, 'SENTRY_NAME', 'SomeName')
    sentry = talisker.flask.sentry(app)
    assert sentry.client.name == 'SomeName'

    response = get_url(app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg['server_name'] == 'SomeName'


def test_flask_sentry_app_tag():
    sentry = talisker.flask.sentry(app)
    response = get_url(app, '/')

    assert response.status_code == 500
    msgs = get_sentry_messages(sentry.client)
    assert msgs[0]['tags']['flask_app'] == app.name


def test_flask_sentry_not_clear_afer_request(monkeypatch):
    tapp = Flask(__name__)

    @tapp.route('/')
    def index():
        return 'ok'

    sentry = talisker.flask.sentry(tapp)
    calls = []
    monkeypatch.setattr(sentry.client.context, 'clear',
                        lambda: calls.append(1))
    get_url(tapp, '/')
    assert len(calls) == 0
    assert isinstance(sentry, talisker.flask.FlaskSentry)


def test_talisker_flask_app():
    tapp = talisker.flask.TaliskerApp(__name__)
    logname = getattr(app, 'logger_name', 'flask.app')

    assert 'sentry' in tapp.extensions
    assert tapp.logger is logging.getLogger(logname)

    if 'LOGGER_HANDLER_POLICY' in tapp.config:
        assert tapp.config['LOGGER_HANDLER_POLICY'] == 'never'


def test_register_app():
    tapp = Flask(__name__)
    talisker.flask.register(tapp)

    logname = getattr(app, 'logger_name', 'flask.app')
    assert 'sentry' in tapp.extensions
    assert tapp.logger is logging.getLogger(logname)
    if 'LOGGER_HANDLER_POLICY' in tapp.config:
        assert tapp.config['LOGGER_HANDLER_POLICY'] == 'never'


def test_flask_view_name_header():
    tapp = Flask(__name__)

    @tapp.route('/')
    def index():
        return 'ok'

    talisker.flask.register(tapp)
    response = get_url(tapp, '/')
    assert response.headers['X-View-Name'] == 'tests.test_flask.index'


def test_flask_view_name_header_no_view(context):
    tapp = Flask(__name__)

    @tapp.route('/')
    def index():
        return 'ok'

    talisker.flask.register(tapp)
    context.logs[:] = []
    response = get_url(tapp, '/notexist')
    assert 'X-View-Name' not in response.headers
    assert context.logs.exists(msg="no flask view for /notexist")


def test_flask_extension_updates_sentry_client():
    orig_client = talisker.sentry.get_client()
    tapp = Flask(__name__)
    ext = talisker.flask.sentry(tapp)
    assert ext.client is not orig_client
    assert talisker.sentry.get_client() is not orig_client
