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

import os
import tempfile

import pytest
from prometheus_client.parser import text_string_to_metric_families
from werkzeug.test import Client
from werkzeug.wrappers import BaseResponse, Response, Request

import talisker.statsd
import talisker.endpoints
import talisker.revision
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


@talisker.endpoints.private
def protected(self, request):
    return Response(status=200)


def get_response(ip, forwarded=None):
    req_dict = {'REMOTE_ADDR': ip}
    if forwarded:
        req_dict['HTTP_X_FORWARDED_FOR'] = forwarded

    return protected(None, Request(req_dict))


def test_private_no_config(monkeypatch):
    set_networks(monkeypatch, '')

    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200

    # double check unicode input
    assert get_response('127.0.0.1').status_code == 200
    assert get_response('1.2.3.4').status_code == 403


def test_private_with_config(monkeypatch):
    set_networks(monkeypatch, '10.0.0.0/8')

    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 5.6.7.8').status_code == 200
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '5.6.7.8').status_code == 403
    assert get_response(b'10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1, 5.6.7.8').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 10.0.0.1').status_code == 403


def test_private_with_multiple_config(monkeypatch):
    set_networks(monkeypatch, '10.0.0.0/8 192.168.0.0/24')

    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 5.6.7.8').status_code == 200
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '5.6.7.8').status_code == 403
    assert get_response(b'10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1, 5.6.7.8').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 10.0.0.1').status_code == 403
    assert get_response(b'192.168.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '192.168.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '192.168.0.1, 5.6.7.8').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 192.168.0.1').status_code == 403


def test_private_response_template(monkeypatch):
    set_networks(monkeypatch, '')

    resp = get_response(b'1.2.3.4')
    assert b"IP address 1.2.3.4" in resp.data
    assert b"REMOTE_ADDR: 1.2.3.4" in resp.data
    assert b"X-Forwarded-For: None" in resp.data
    resp = get_response(b'1.2.3.4', '10.0.0.1, 192.168.0.1')
    assert b"IP address 10.0.0.1" in resp.data
    assert b"REMOTE_ADDR: 1.2.3.4" in resp.data
    assert b"X-Forwarded-For: 10.0.0.1, 192.168.0.1" in resp.data


def test_unknown_endpoint(client):
    response = client.get('/_status/unknown')
    assert response.status_code == 404


def test_unmapped_endpoint_method(client):
    response = client.get('/_status/__call__')
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
    talisker.revision.set('unknown')
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
    talisker.revision.set('unknown')

    def app(e, sr):
        yield b'app'
        sr('404', [])
        yield b'iterator'

    c = client(app)
    response = c.get('/_status/check')
    assert response.data == b'unknown'


def test_check_with_app_url_iterator():

    def app(e, sr):
        yield b'app'
        sr('200', [])
        yield b'iterator'

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


@pytest.mark.parametrize('error_url', (
    '/_status/error',
    '/_status/test/sentry',
))
def test_error(client, error_url):
    response = client.get(error_url,
                          environ_overrides={'REMOTE_ADDR': b'1.2.3.4'})
    assert response.status_code == 403
    with pytest.raises(talisker.endpoints.TestException):
        client.get(error_url,
                   environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})


def test_statsd_metric(client, statsd_metrics):
    statsd = talisker.statsd.get_client()
    env = {'statsd': statsd,
           'REMOTE_ADDR': b'127.0.0.1'}

    with statsd.collect() as stats:
        response = client.get('/_status/test/statsd',
                              environ_overrides=env)
        assert stats[0] == 'test:1|c'

    assert response.status_code == 200


def test_metrics(client, prometheus_metrics):
    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'1.2.3.4'})
    assert response.status_code == 403
    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert list(text_string_to_metric_families(response.data.decode()))


def test_metrics_no_prometheus(client, monkeypatch):
    monkeypatch.setattr(
        talisker.endpoints, 'pkg_is_installed', lambda x: False)
    response = client.get(
        '/_status/metrics', environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 501
    response = client.get(
        '/_status/test/prometheus',
        environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 501


def test_prometheus_metric(client, prometheus_metrics):
    response = client.get('/_status/test/prometheus',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert b'# HELP test test\n# TYPE test counter\ntest 1.0' in response.data
