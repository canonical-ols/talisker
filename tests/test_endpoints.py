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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import os
import tempfile

import pytest
from werkzeug.test import Client
from werkzeug.wrappers import BaseResponse, Response, Request

import talisker.statsd
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


def set_networks(monkeypatch, networks):
    monkeypatch.setitem(os.environ, 'TALISKER_NETWORKS', networks)
    monkeypatch.setattr(talisker.endpoints, '_loaded', False)


@talisker.endpoints.private
def protected(self, request):
    return Response(status=200)


def test_private_no_config(monkeypatch):
    set_networks(monkeypatch, '')

    response = protected(None, Request({'REMOTE_ADDR': b'127.0.0.1'}))
    assert response.status_code == 200
    response = protected(None, Request({'REMOTE_ADDR': '127.0.0.1'}))
    assert response.status_code == 200
    response = protected(None, Request({'REMOTE_ADDR': b'1.2.3.4'}))
    assert response.status_code == 403
    response = protected(None, Request({'REMOTE_ADDR': '1.2.3.4'}))
    assert response.status_code == 403


def test_private_with_config(monkeypatch):
    set_networks(monkeypatch, '10.0.0.0/8')

    response = protected(None, Request({'REMOTE_ADDR': b'127.0.0.1'}))
    assert response.status_code == 200
    response = protected(None, Request({'REMOTE_ADDR': b'1.2.3.4'}))
    assert response.status_code == 403
    response = protected(None, Request({'REMOTE_ADDR': b'10.0.0.1'}))
    assert response.status_code == 200


def test_private_with_multiple_config(monkeypatch):
    set_networks(monkeypatch, '10.0.0.0/8 192.168.0.0/24')

    response = protected(None, Request({'REMOTE_ADDR': b'127.0.0.1'}))
    assert response.status_code == 200
    response = protected(None, Request({'REMOTE_ADDR': b'1.2.3.4'}))
    assert response.status_code == 403
    response = protected(None, Request({'REMOTE_ADDR': b'10.0.0.1'}))
    assert response.status_code == 200
    response = protected(None, Request({'REMOTE_ADDR': b'192.168.0.1'}))
    assert response.status_code == 200


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


def test_ping(client, monkeypatch):
    monkeypatch.chdir(tempfile.mkdtemp())
    response = client.get('/_status/ping')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'unknown'


def test_check_no_app_url():
    c = client(wsgi_app('404'))
    response = c.get('/_status/check')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'unknown'


def test_check_with_app_url():

    def app(e, sr):
        """Implements custom check check"""
        if e['PATH_INFO'] == '/_status/check':
            sr('200', [])
            return b'app implemented check'
        else:
            sr('404', [])
            return ''

    c = client(app)
    response = c.get('/_status/check')
    assert response.data == b'app implemented check'


def test_check_with_no_app_url_iterator():

    def app(e, sr):
        yield 'app'
        sr('404', [])
        yield 'iterator'

    c = client(app)
    response = c.get('/_status/check')
    assert response.data == b'unknown'


def test_check_with_app_url_iterator():

    def app(e, sr):
        yield 'app'
        sr('200', [])
        yield 'iterator'

    c = client(app)
    response = c.get('/_status/check')
    assert response.data == b'appiterator'


def test_check_with_exc_info():
    def app(e, sr):
        try:
            raise Exception('test')
        except:
            sr(500, [], exc_info=1)
            return ''

    c = client(app)
    response = c.get('/_status/check')
    assert response.data == b'error'
    assert response.status_code == 500


def test_error(client):
    response = client.get('/_status/error',
                          environ_overrides={'REMOTE_ADDR': b'1.2.3.4'})
    assert response.status_code == 403
    with pytest.raises(talisker.endpoints.TestException):
        client.get('/_status/error',
                   environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})


def test_metric(client):
    pipeline = talisker.statsd.get_client().pipeline()
    env = {'statsd': pipeline,
           'REMOTE_ADDR': b'127.0.0.1'}
    response = client.get('/_status/metric', environ_overrides=env)
    assert response.status_code == 200
    assert pipeline._stats[0] == 'test:1|c'
