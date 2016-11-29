from flask import Flask


import talisker.flask

from tests import conftest

app = Flask(__name__)


@app.route('/')
def error():
    raise Exception('app exception')


def flask_sentry():
    client = talisker.flask.get_flask_sentry_client.uncached(
        app, dsn=conftest.DSN, transport=conftest.DummyTransport)
    sentry = talisker.flask.sentry(app, client=client)
    return sentry


def test_flask_sentry_sends_message():
    sentry = flask_sentry()
    app_client = app.test_client()
    with app.app_context():
        response = app_client.get('/')

    assert response.status_code == 500

    messages = conftest.sentry_messages(sentry.client)
    assert len(messages) == 1
    msg = messages[0]
    assert msg['culprit'] == '/'


def test_flask_sentry_default_include_paths():
    sentry = flask_sentry()
    assert sentry.client.include_paths == set(['tests.test_flask'])


def test_flask_sentry_app_tag():
    sentry = flask_sentry()
    app_client = app.test_client()
    with app.app_context():
        response = app_client.get('/')

    assert response.status_code == 500

    messages = conftest.sentry_messages(sentry.client)
    msg = messages[0]

    assert msg['tags']['flask_app'] == app.name
