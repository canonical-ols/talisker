from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import pytest
from werkzeug.test import Client
from werkzeug.wrappers import BaseResponse

import talisker.endpoints
from talisker.endpoints import StandardEndpointMiddleware


@pytest.fixture
def wsgi_app(status='200', headers=[], body=''):
    def app(environ, start_response):
        start_response(status, headers)
        return body
    return app


@pytest.fixture
def client(wsgi_app):
    app = StandardEndpointMiddleware(wsgi_app)
    return Client(app, BaseResponse)


def test_unknown_endpoint(client):
    response = client.get('/_status/unknown')
    assert response.status_code == 404


def test_pass_thru():
    c = client(wsgi_app(body='test'))
    response = c.get('/something')
    assert response.status_code == 200
    assert response.data == b'test'


def test_index_endpoint(client):
    response = client.get('/_status/')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/html; charset=utf-8'


def test_index_redirect(client):
    response = client.get('/_status')
    assert response.status_code == 302
    assert response.headers['Location'] == '/_status/'


def test_haproxy(client):
    response = client.get('/_status/haproxy')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'OK'


def test_haproxy_inactive(client, monkeypatch):
    monkeypatch.setitem(talisker.endpoints.app_data, 'active', False)
    response = client.get('/_status/haproxy')
    assert response.status_code == 404
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'biab, lol'


def test_nagios_no_app_url():
    c = client(wsgi_app('404'))
    response = c.get('/_status/nagios')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'OK'


def test_nagios_with_app_url():

    def app(e, sr):
        """Implements custom nagios check"""
        if e['PATH_INFO'] == '/_status/nagios':
            sr('200', [])
            return b'app implemented nagios'
        else:
            sr('404', [])
            return ''

    c = client(app)
    response = c.get('/_status/nagios')
    assert response.data == b'app implemented nagios'


def test_version_unknown(client):
    response = client.get('/_status/version')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'unknown'


def test_version(client, monkeypatch):
    monkeypatch.setitem(talisker.endpoints.app_data, 'version', 'r1234')
    response = client.get('/_status/version')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'r1234'


def test_error(client):
    with pytest.raises(talisker.endpoints.TestException):
        client.get('/_status/error')
