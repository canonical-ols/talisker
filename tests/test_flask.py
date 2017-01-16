from flask import Flask

import talisker.flask

from tests import conftest


class IgnoredException(Exception):
    pass


app = Flask(__name__)


@app.route('/')
def error():
    raise Exception('app exception')


@app.route('/ignored')
def ignored():
    raise IgnoredException('test exception')


def get_url(*args, **kwargs):
    app_client = app.test_client()
    with app.app_context():
        return app_client.get(*args, **kwargs)


def flask_sentry():
    """Get a test sentry client"""
    config = {
        'transport': conftest.DummyTransport,
        'dsn': conftest.DSN,
    }
    return talisker.flask.sentry(app, client_config=config)


def test_flask_sentry_sends_message():
    sentry = flask_sentry()
    response = get_url('/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 1
    msg = messages[0]
    assert msg['culprit'] == '/'


def test_flask_sentry_default_include_paths():
    sentry = flask_sentry()
    assert sentry.client.include_paths == set(['tests.test_flask'])


def test_flask_sentry_uses_app_config_to_ingnore_exc(monkeypatch):
    monkeypatch.setitem(app.config, 'SENTRY_CONFIG', {
        'ignore_exceptions': ['IgnoredException']
    })
    sentry = flask_sentry()

    assert 'IgnoredException' in sentry.client.ignore_exceptions

    response = get_url('/ignored')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 0


def test_flask_sentry_uses_app_config_to_set_name(monkeypatch):
    monkeypatch.setitem(app.config, 'SENTRY_NAME', 'SomeName')
    sentry = flask_sentry()
    assert sentry.client.name == 'SomeName'

    response = get_url('/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 1
    msg = messages[0]
    assert msg['server_name'] == 'SomeName'


def test_flask_sentry_app_tag():
    sentry = flask_sentry()
    response = get_url('/')

    assert response.status_code == 500
    messages = conftest.sentry_messages(sentry.client)
    msg = messages[0]
    assert msg['tags']['flask_app'] == app.name
