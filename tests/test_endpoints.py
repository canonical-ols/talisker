#
# Copyright (c) 2015-2021 Canonical, Ltd.
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

import pytest
from werkzeug.test import Client, EnvironBuilder
from werkzeug.wrappers import Response, Request

import talisker.statsd
import talisker.endpoints
from talisker.endpoints import StandardEndpointMiddleware

from tests.test_metrics import counter_name


def wsgi_app(status='200', headers=[], body=''):
    def app(environ, start_response):
        start_response(status, headers)
        return body
    return app


def get_client(app=None):
    if app is None:
        app = wsgi_app()
    newapp = StandardEndpointMiddleware(app)
    return Client(newapp, Response)


@talisker.endpoints.private
def protected(self, request):
    return Response(status=200)


def get_response(ip, forwarded=None):
    req_dict = {'REMOTE_ADDR': ip}
    if forwarded:
        req_dict['HTTP_X_FORWARDED_FOR'] = forwarded

    return protected(None, Request(req_dict))


def test_private_no_config(config):
    config['TALISKER_NETWORKS'] = ''

    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200

    # double check unicode input
    assert get_response('127.0.0.1').status_code == 200
    assert get_response('1.2.3.4').status_code == 403


def test_private_with_config(config):
    config['TALISKER_NETWORKS'] = '10.0.0.0/8'
    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 5.6.7.8').status_code == 403
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '5.6.7.8').status_code == 403
    assert get_response(b'10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1, 5.6.7.8').status_code == 403


def test_private_with_multiple_config(config):
    config['TALISKER_NETWORKS'] = '10.0.0.0/8 192.168.0.0/24'

    assert get_response(b'127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '127.0.0.1, 5.6.7.8').status_code == 403
    assert get_response(b'1.2.3.4').status_code == 403
    assert get_response(b'1.2.3.4', '5.6.7.8').status_code == 403
    assert get_response(b'10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 10.0.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '10.0.0.1, 5.6.7.8').status_code == 403
    assert get_response(b'192.168.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '192.168.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '5.6.7.8, 192.168.0.1').status_code == 200
    assert get_response(b'1.2.3.4', '192.168.0.1, 5.6.7.8').status_code == 403


def test_private_response_template(config):
    config['TALISKER_NETWORKS'] = ''

    resp = get_response(b'1.2.3.4')
    assert b"IP address 1.2.3.4" in resp.data
    assert b"REMOTE_ADDR: 1.2.3.4" in resp.data
    assert b"X-Forwarded-For: None" in resp.data
    resp = get_response(b'1.2.3.4', '10.0.0.1, 192.168.0.1')
    assert b"IP address 192.168.0.1" in resp.data
    assert b"REMOTE_ADDR: 1.2.3.4" in resp.data
    assert b"X-Forwarded-For: 10.0.0.1, 192.168.0.1" in resp.data


def test_unknown_endpoint():
    client = get_client()
    response = client.get('/_status/unknown')
    # passed through to app
    assert response.status_code == 200


def test_pass_thru():
    c = get_client(wsgi_app(body='test'))
    response = c.get('/something')
    assert response.status_code == 200
    assert response.data == b'test'


def test_status_interface(config):

    # FakeSocket is to emulate a socket object as
    # used in the gunicorn specific `gunicorn.socket`
    # environment variable on the WSGI request
    class FakeSocket():
        def __init__(self, ip, port):
            self.ip = ip
            self.port = port

        def getsockname(self):
            return self.ip, self.port

    config['TALISKER_STATUS_INTERFACE'] = '10.0.0.1'
    config['TALISKER_REVISION_ID'] = 'test-rev-id'
    c = get_client(wsgi_app('404'))
    environ = EnvironBuilder('/_status/check', environ_overrides={
        'gunicorn.socket': FakeSocket('127.0.0.1', 8000)})
    response = c.open(environ)
    assert response.status_code == 404

    environ.environ_overrides['gunicorn.socket'] = FakeSocket('10.0.0.1', 8000)
    response = c.open(environ)
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'test-rev-id\n'


def test_index_endpoint():
    client = get_client()
    response = client.get('/_status')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'


def test_index_trailing_slash():
    client = get_client()
    response = client.get('/_status/')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'


def test_ping(config):
    client = get_client()
    response = client.get('/_status/ping')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'test-rev-id\n'


def test_check_no_app_url(config):
    c = get_client(wsgi_app('404'))
    response = c.get('/_status/check')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
    assert response.data == b'test-rev-id\n'


def test_check_with_app_url():

    def app(e, sr):
        """Implements custom check check"""
        if e['PATH_INFO'] == '/_status/check':
            sr('200', [])
            return b'app implemented check'
        else:
            sr('404', [])
            return ''

    c = get_client(app)
    response = c.get('/_status/check')
    assert response.data == b'app implemented check'


def test_check_with_no_app_url_iterator(config):
    def app(e, sr):
        yield b'app'
        sr('404', [])
        yield b'iterator'

    c = get_client(app)
    response = c.get('/_status/check')
    assert response.data == b'test-rev-id\n'


def test_check_with_app_url_iterator():

    def app(e, sr):
        yield b'app'
        sr('200', [])
        yield b'iterator'

    c = get_client(app)
    response = c.get('/_status/check')
    assert response.data == b'appiterator'


def test_check_with_exc_info():
    def app(e, sr):
        try:
            raise Exception('test')
        except Exception:
            sr(500, [], exc_info=1)
            return ''

    c = get_client(app)
    response = c.get('/_status/check')
    assert response.data == b'error'
    assert response.status_code == 500


def test_sentry():
    client = get_client()
    response = client.get('/_status/test/sentry',
                          environ_overrides={'REMOTE_ADDR': b'1.2.3.4'})
    assert response.status_code == 403
    with pytest.raises(talisker.endpoints.TestException):
        client.get('/_status/test/sentry',
                   environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})


def test_statsd_metric(context):
    client = get_client()
    statsd = talisker.statsd.get_client()
    env = {'statsd': statsd,
           'REMOTE_ADDR': b'127.0.0.1'}

    response = client.get('/_status/test/statsd', environ_overrides=env)

    assert context.statsd[0] == 'test:1|c'
    assert response.status_code == 200


def test_metrics():
    try:
        from prometheus_client.parser import text_string_to_metric_families
    except ImportError:
        pytest.skip('need prometheus_client installed')

    client = get_client()
    response = client.get('/_status/test/prometheus',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200

    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'1.2.3.4'})
    assert response.status_code == 403
    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert list(text_string_to_metric_families(response.data.decode()))


def test_metrics_no_prometheus(monkeypatch):
    monkeypatch.setattr(
        talisker.endpoints, 'pkg_is_installed', lambda x: False)
    client = get_client()
    response = client.get(
        '/_status/metrics', environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 501
    response = client.get(
        '/_status/test/prometheus',
        environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 501


def test_prometheus_metric():
    client = get_client()
    response = client.get('/_status/test/prometheus',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    response = client.get('/_status/metrics',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    output = response.data.decode('utf8')
    name = counter_name('test_total')
    assert '# HELP {} Multiprocess metric\n'.format(name) in output
    assert '# TYPE {} counter'.format(name) in output
    assert '{} 1.0'.format(name) in output


def test_info_packages():
    client = get_client()
    response = client.get('/_status/info/packages',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'


def test_info_workers():
    client = get_client()
    response = client.get('/_status/info/workers',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'


def test_info_objgraph():
    client = get_client()
    response = client.get('/_status/info/objgraph',
                          environ_overrides={'REMOTE_ADDR': b'127.0.0.1'})
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/plain; charset=utf-8'
