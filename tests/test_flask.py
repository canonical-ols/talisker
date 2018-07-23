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

from flask import Flask

import talisker.flask

from tests import conftest


class IgnoredException(Exception):
    pass


app = Flask(__name__)
app.config['SENTRY_TRANSPORT'] = conftest.DummyTransport
app.config['SENTRY_DSN'] = conftest.DSN


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


def flask_sentry():
    """Get a test sentry client"""
    return talisker.flask.sentry(app)


def test_flask_sentry_sends_message():
    sentry = talisker.flask.sentry(app)
    response = get_url(app, '/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 1
    msg = messages[0]
    if 'culprit' in msg:
        assert msg['culprit'] == '/'
    else:
        assert msg['transaction'] == '/'


def test_flask_sentry_default_include_paths():
    sentry = talisker.flask.sentry(app)
    assert sentry.client.include_paths == set(['tests.test_flask'])


def test_flask_sentry_uses_app_config_to_ingnore_exc(monkeypatch):
    monkeypatch.setitem(app.config, 'SENTRY_CONFIG', {
        'ignore_exceptions': ['IgnoredException']
    })
    sentry = talisker.flask.sentry(app)

    assert 'IgnoredException' in sentry.client.ignore_exceptions

    response = get_url(app, '/ignored')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 0


def test_flask_sentry_uses_app_config_to_set_name(monkeypatch):
    monkeypatch.setitem(app.config, 'SENTRY_NAME', 'SomeName')
    sentry = talisker.flask.sentry(app)
    assert sentry.client.name == 'SomeName'

    response = get_url(app, '/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 1
    msg = messages[0]
    assert msg['server_name'] == 'SomeName'


def test_flask_sentry_app_tag():
    sentry = talisker.flask.sentry(app)
    response = get_url(app, '/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    msg = messages[0]
    assert msg['tags']['flask_app'] == app.name


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


def test_flask_view_name_header_no_view(log):
    tapp = Flask(__name__)

    @tapp.route('/')
    def index():
        return 'ok'

    talisker.flask.register(tapp)
    log[:] = []
    response = get_url(tapp, '/notexist')
    assert 'X-View-Name' not in response.headers
    assert log[0].msg == "no flask view for /notexist"
