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

from datetime import timedelta
from io import StringIO

from collections import namedtuple
import datetime
import http.client
import io
import itertools
import raven.context
import requests
import responses
import socket
from future.moves.urllib.parse import urlunsplit

from freezegun import freeze_time
import pytest
import urllib3
from werkzeug.local import release_local

import talisker.requests
import talisker.statsd


def request(method='GET', host='http://example.com', url='/', **kwargs):
    req = requests.Request(method, url=host + url, **kwargs)
    return req.prepare()


def mock_response(
        req=None,
        code=200,
        view=None,
        body=None,
        content_type='text/plain',
        headers={},
        elapsed=1.0):
    if req is None:
        req = request()
    resp = requests.Response()
    resp.request = req
    resp.status_code = code
    resp.elapsed = timedelta(seconds=elapsed)
    resp.headers['Server'] = 'test/1.0'
    if body is not None:
        resp.raw = StringIO(body)
        resp.headers['Content-Length'] = len(body)
        resp.headers['Content-Type'] = content_type
    if view is not None:
        resp.headers['X-View-Name'] = view
    resp.headers.update(headers)
    return resp


def test_collect_metadata():
    req = request(url='/foo/bar')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://example.com/foo/bar',
        'method': 'GET',
        'host': 'example.com',
    }


@pytest.fixture
def requests_hosts(monkeypatch):
    monkeypatch.setattr(talisker.requests, 'HOSTS', {})


def test_collect_metadata_hostname(requests_hosts):
    talisker.requests.register_endpoint_name('1.2.3.4:8000', 'service')
    req = request(url='/foo/bar', host='http://1.2.3.4:8000')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://service:8000/foo/bar',
        'method': 'GET',
        'host': 'service',
        'netloc': '1.2.3.4:8000',
    }


def test_collect_metadata_request_body():
    req = request(method='POST', url='/foo/bar', json=u'"some data"')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://example.com/foo/bar',
        'method': 'POST',
        'host': 'example.com',
        'request_type': 'application/json',
        'request_size': 15,
    }


def test_collect_metadata_querystring():
    req = request(url='/foo/bar?baz=1&qux=data')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://example.com/foo/bar?',
        'qs': '?baz=<len 1>&qux=<len 4>',
        'qs_size': 14,
        'method': 'GET',
        'host': 'example.com',
    }


def test_collect_metadata_with_response():
    req = request(url='/foo/bar')
    resp = mock_response(req, view='views.name', body=u'some content')
    metadata = talisker.requests.collect_metadata(req, resp)
    assert metadata == {
        'url': 'http://example.com/foo/bar',
        'method': 'GET',
        'host': 'example.com',
        'status_code': 200,
        'view': 'views.name',
        'server': 'test/1.0',
        'duration_ms': 1000,
        'response_type': 'text/plain',
        'response_size': 12,
    }


def test_metric_hook(context):
    r = mock_response(view='view')

    with raven.context.Context() as ctx:
        talisker.requests.metrics_response_hook(r)

    assert context.statsd[0] == 'requests.count.example-com.view:1|c'
    assert context.statsd[1] == (
        'requests.latency.example-com.view.200:1000.000000|ms'
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://example.com/'
    assert breadcrumbs[0]['data']['host'] == 'example.com'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['view'] == 'view'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration_ms'] == 1000.0


def test_metric_hook_user_name(context):
    r = mock_response(view='view')

    with raven.context.Context() as ctx:
        talisker.requests._local.metric_api_name = 'api'
        talisker.requests._local.metric_host_name = 'service'
        talisker.requests.metrics_response_hook(r)
        release_local(talisker.requests._local)

    assert context.statsd[0] == 'requests.count.service.api:1|c'
    assert context.statsd[1] == (
        'requests.latency.service.api.200:1000.000000|ms'
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://example.com/'
    assert breadcrumbs[0]['data']['host'] == 'example.com'
    assert breadcrumbs[0]['data']['view'] == 'view'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration_ms'] == 1000.0


def test_metric_hook_registered_endpoint(requests_hosts, context):
    talisker.requests.register_endpoint_name('1.2.3.4', 'service')
    req = request(host='http://1.2.3.4', url='/foo/bar?a=1')
    resp = mock_response(req, view='view')

    with raven.context.Context() as ctx:
        talisker.requests.metrics_response_hook(resp)

    assert context.statsd[0] == 'requests.count.service.view:1|c'
    assert context.statsd[1] == (
        'requests.latency.service.view.200:1000.000000|ms'
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://service/foo/bar?'
    assert breadcrumbs[0]['data']['host'] == 'service'
    assert breadcrumbs[0]['data']['netloc'] == '1.2.3.4'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['view'] == 'view'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration_ms'] == 1000.0


@responses.activate
def test_configured_session(context):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(
        responses.GET,
        'http://localhost/foo/bar',
        body='OK',
        headers={'X-View-Name': 'view'},
    )

    with talisker.request_id.context('XXX'):
        with raven.context.Context() as ctx:
            session.get('http://localhost/foo/bar')

    for header_name in responses.calls[0].request.headers:
        assert isinstance(header_name, str)
    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert context.statsd[0] == 'requests.count.localhost.view:1|c'
    assert context.statsd[1].startswith(
        'requests.latency.localhost.view.200:')
    breadcrumbs = ctx.breadcrumbs.get_buffer()

    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://localhost/foo/bar'
    assert breadcrumbs[0]['data']['host'] == 'localhost'
    assert breadcrumbs[0]['data']['view'] == 'view'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert 'duration_ms' in breadcrumbs[0]['data']


@responses.activate
def test_configured_session_http_error(context):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(
        responses.GET,
        'http://localhost/foo/bar',
        status=500,
        body='NOT OK',
        headers={'X-View-Name': 'view'},
    )

    with raven.context.Context() as ctx:
        session.get('http://localhost/foo/bar')

    assert context.statsd[0] == 'requests.count.localhost.view:1|c'
    assert context.statsd[1].startswith('requests.latency.localhost.view.500:')
    assert context.statsd[2] == (
        'requests.errors.localhost.http.view.500:1|c'
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()

    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://localhost/foo/bar'
    assert breadcrumbs[0]['data']['host'] == 'localhost'
    assert breadcrumbs[0]['data']['view'] == 'view'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 500
    assert 'duration_ms' in breadcrumbs[0]['data']


def test_configured_session_connection_error(context):
    session = requests.Session()
    talisker.requests.configure(session)

    with raven.context.Context() as ctx:
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get('http://nope.nowhere/foo')

    assert context.statsd[0] == 'requests.count.nope-nowhere.unknown:1|c'
    assert context.statsd[1].startswith(
        'requests.errors.nope-nowhere.connection.unknown.')
    # error code depends on python version host dns set up
    assert any((
        context.statsd[1].endswith('unknown:1|c'),
        context.statsd[1].endswith('EAI_NONAME:1|c'),
        context.statsd[1].endswith('EAI_AGAIN:1|c'),
    ))

    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[-1]['type'] == 'http'
    assert breadcrumbs[-1]['category'] == 'requests'
    assert breadcrumbs[-1]['data']['url'] == 'http://nope.nowhere/foo'
    assert breadcrumbs[-1]['data']['host'] == 'nope.nowhere'
    assert breadcrumbs[-1]['data']['method'] == 'GET'
    if 'errno' in breadcrumbs[-1]['data']:
        assert any((
            breadcrumbs[-1]['data']['errno'] == 'EAI_NONAME',
            breadcrumbs[-1]['data']['errno'] == 'EAI_AGAIN',
        ))


@responses.activate
def test_configured_session_with_user_name(context):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(responses.GET, 'http://localhost/foo/bar', body='OK')

    with talisker.request_id.context('XXX'):
        session.get(
            'http://localhost/foo/bar',
            metric_api_name='api',
            metric_host_name='service',
        )

    for header_name in responses.calls[0].request.headers:
        assert isinstance(header_name, str)
    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert context.statsd[0].startswith('requests.count.service.api:')
    assert context.statsd[1].startswith('requests.latency.service.api.200:')


@responses.activate
def test_adapter_balances():
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter(
        ['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000'],
    )
    session.mount('http://name', adapter)
    responses.add('GET', 'http://1.2.3.4:8000/foo', body='1')
    responses.add('GET', 'http://1.2.3.4:8001/foo', body='2')
    responses.add('GET', 'http://4.3.2.1:8000/foo', body='3')

    result = session.get('http://name/foo').text
    result += session.get('http://name/foo').text
    result += session.get('http://name/foo').text
    assert ''.join(sorted(result)) == '123'


def test_adapter_adds_default_timeout(monkeypatch):
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter()
    session.mount('http://name', adapter)
    kws = {}

    def timeouts(*args, **kwargs):
        kws.update(kwargs)
        return requests.Response()

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', timeouts)
    session.get('http://name/foo')
    assert kws['timeout'] == (1.0, 10.0)


class FakeSocket():
    """Pretend to be read only socket-like object that implements makefile."""
    def __init__(self, content):
        self.content = content

    def makefile(self, mode, buffer=None):
        return io.BytesIO(self.content)


class RequestData(namedtuple('RequestData', 'pool conn method url kwargs')):

    @property
    def full_url(self):
        netloc = self.conn.host
        if self.conn.port:
            netloc += ':{}'.format(self.conn.port)
        return urlunsplit((
            self.pool.scheme,
            netloc,
            self.url,
            None,
            None,
        ))

    @property
    def read_timeout(self):
        return self.kwargs['timeout'].read_timeout

    @property
    def connect_timeout(self):
        return self.kwargs['timeout'].connect_timeout

    @property
    def timeout(self):
        return self.connect_timeout, self.read_timeout


class Urllib3Mock:
    """Helper to mock out urllib3 requests and timings."""
    def __init__(self, frozen_time):
        self.frozen_time = frozen_time
        self.requests = []
        self.response_iter = None

    def set_response(self, content, status='200 OK', headers={}, latency=1.0):
        """Set the response to any requests."""
        self.response_iter = itertools.cycle(
            [((content, status, headers), latency)]
        )

    def set_error(self, error, latency=1.0):
        """Raise an error for all requests."""
        assert isinstance(error, Exception)
        self.response_iter = itertools.cycle([(error, latency)])

    def set_responses(self, responses):
        """Respond to requests with provided responses in order.

        Responses can be Exceptions to raise or a http.client.HTTPResponse."""
        self.response_iter = iter(responses)

    def make_response(self, content, status='200 OK', headers={}):
        """Make a fake http.client.HTTPResponse based on a byte stream."""
        formatted_headers = '\r\n'.join(
            '{}: {}'.format(k, v) for k, v in headers.items()
        )
        stream = 'HTTP/1.1 {}\r\n{}\r\n{}'.format(
            status, formatted_headers, content,
        )
        sock = FakeSocket(stream.encode('utf8'))
        response = http.client.HTTPResponse(sock)
        response.begin()  # parse the stream
        return response

    def make_request(self, pool, conn, method, url, **kwargs):
        """A mock replacement for urllib3.HTTPConnectionPool._make_request."""
        rdata = RequestData(pool, conn, method, url, kwargs)
        self.requests.append(rdata)

        assert self.response_iter, 'no responses set'

        response, latency = next(self.response_iter)
        self.frozen_time.tick(datetime.timedelta(seconds=latency))

        if isinstance(response, Exception):
            raise response
        elif isinstance(response, http.client.HTTPResponse):
            return response
        elif isinstance(response, str):
            return self.make_response(response)
        else:
            return self.make_response(*response)

    @property
    def call_list(self):
        return [(r.full_url, r.timeout) for r in self.requests]


@pytest.fixture
def mock_urllib3(monkeypatch):
    freeze = freeze_time()
    frozen = freeze.start()
    mock = Urllib3Mock(frozen)

    def sleep(amount):
        frozen.tick(datetime.timedelta(seconds=amount))

    # use a function to wrap the method, so we preserve original calling self
    # reference, rather than our method's self.
    def _make_request(*args, **kwargs):
        return mock.make_request(*args, **kwargs)

    monkeypatch.setattr(
        urllib3.HTTPConnectionPool, '_make_request', _make_request)
    monkeypatch.setattr(urllib3.util.retry.time, 'sleep', sleep)
    yield mock
    freeze.stop()


def test_adapter_default_no_retries(mock_urllib3):
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter()
    session.mount('http://name', adapter)

    mock_urllib3.set_error(socket.error())

    with pytest.raises(requests.ConnectionError):
        session.get('http://name')

    assert len(mock_urllib3.requests) == 1


@pytest.mark.parametrize('urllib3_error, requests_error', [
    (urllib3.exceptions.ConnectTimeoutError(None, 'error'),
        requests.ConnectionError),
    (socket.error(), requests.ConnectionError),
])
def test_adapter_retry_on_errors(mock_urllib3, urllib3_error, requests_error):
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter(
        itertools.cycle(['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000']),
        max_retries=urllib3.Retry(3, backoff_factor=1),
    )
    session.mount('http://name', adapter)
    mock_urllib3.set_error(urllib3_error)

    with pytest.raises(requests_error):
        session.get('http://name/foo')

    assert mock_urllib3.call_list == [
        ('http://1.2.3.4:8000/foo', (1.0, 10.0)),
        ('http://1.2.3.4:8001/foo', (1.0, 9.0)),
        ('http://4.3.2.1:8000/foo', (1.0, 6.0)),
        ('http://1.2.3.4:8000/foo', (1.0, 1.0)),
    ]


def test_adapter_no_retry_on_read_timeout(mock_urllib3):
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter(
        ['1.2.3.4:8000'],
        max_retries=urllib3.Retry(3),
    )
    session.mount('http://name', adapter)

    mock_urllib3.set_error(
        urllib3.exceptions.ReadTimeoutError(None, '/', 'error')
    )
    with pytest.raises(requests.Timeout):
        session.get('http://name/foo')

    urls = list(request.full_url for request in mock_urllib3.requests)
    assert urls == ['http://1.2.3.4:8000/foo']


def test_adapter_retry_on_status_raises(mock_urllib3):
    session = requests.Session()
    retry = urllib3.Retry(3, backoff_factor=1, status_forcelist=[503])
    adapter = talisker.requests.TaliskerAdapter(
        itertools.cycle(['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000']),
        max_retries=retry,
    )
    session.mount('http://name', adapter)

    mock_urllib3.set_response('OH NOES', '503 Service Unavailable')

    with pytest.raises(requests.exceptions.RetryError):
        session.get('http://name/foo')

    assert mock_urllib3.call_list == [
        ('http://1.2.3.4:8000/foo', (1.0, 10.0)),
        ('http://1.2.3.4:8001/foo', (1.0, 9.0)),
        ('http://4.3.2.1:8000/foo', (1.0, 6.0)),
        ('http://1.2.3.4:8000/foo', (1.0, 1.0)),
    ]


def test_adapter_retry_on_status_returns_when_no_raise(mock_urllib3):
    session = requests.Session()
    retry = urllib3.Retry(
        3, backoff_factor=1, status_forcelist=[503], raise_on_status=False,
    )
    adapter = talisker.requests.TaliskerAdapter(
        itertools.cycle(['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000']),
        max_retries=retry,
    )
    session.mount('http://name', adapter)

    mock_urllib3.set_response('OH NOES', '503 Service Unavailable')
    response = session.get('http://name/foo')
    assert response.status_code == 503
    assert response.content == b'OH NOES'

    assert mock_urllib3.call_list == [
        ('http://1.2.3.4:8000/foo', (1.0, 10.0)),
        ('http://1.2.3.4:8001/foo', (1.0, 9.0)),
        ('http://4.3.2.1:8000/foo', (1.0, 6.0)),
        ('http://1.2.3.4:8000/foo', (1.0, 1.0)),
    ]


def test_adapter_retry_on_status_header(mock_urllib3):
    session = requests.Session()
    retry = urllib3.Retry(3, backoff_factor=1, status_forcelist=[503])
    adapter = talisker.requests.TaliskerAdapter(
        itertools.cycle(['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000']),
        max_retries=retry,
    )
    session.mount('http://name', adapter)

    headers = {'Retry-After': '1'}
    mock_urllib3.set_response(
        'OH NOES', '503 Service Unavailable', headers)

    with pytest.raises(requests.exceptions.RetryError):
        session.get('http://name/foo')

    assert mock_urllib3.call_list == [
        ('http://1.2.3.4:8000/foo', (1.0, 10.0)),
        ('http://1.2.3.4:8001/foo', (1.0, 8.0)),
        ('http://4.3.2.1:8000/foo', (1.0, 6.0)),
        ('http://1.2.3.4:8000/foo', (1.0, 4.0)),
    ]


@pytest.mark.parametrize('retry, response', [
    (None, socket.error()),
    (urllib3.Retry(1), socket.error()),
    (urllib3.Retry(1, status_forcelist=[500]),
        ('ERROR', '500 Internal Server Error')),
])
def test_adapter_exceptions_match_default(mock_urllib3, retry, response):
    session = requests.Session()
    session.mount(
        'http://default',
        requests.adapters.HTTPAdapter(max_retries=retry),
    )
    session.mount(
        'http://talisker',
        talisker.requests.TaliskerAdapter(max_retries=retry),
    )
    if isinstance(response, Exception):
        mock_urllib3.set_error(response)
    else:
        mock_urllib3.set_response(*response)

    exc = None
    try:
        session.get('http://default/')
    except Exception as e:
        exc = e

    with pytest.raises(exc.__class__):
        session.get('http://talisker/')


def test_adapter_timeout_formats(mock_urllib3):
    session = requests.Session()
    retry = urllib3.Retry(3, backoff_factor=1)
    no_retries = urllib3.Retry(0, read=False)
    adapter = talisker.requests.TaliskerAdapter(['1.2.4.5'], max_retries=retry)
    session.mount('http://name', adapter)

    mock_urllib3.set_error(socket.error())

    with pytest.raises(requests.ConnectionError):
        session.get('http://name/foo', timeout=no_retries)
    assert len(mock_urllib3.requests) == 1
    assert mock_urllib3.requests[-1].timeout == (1.0, 10.0)

    with pytest.raises(requests.ConnectionError):
        session.get('http://name/foo', timeout=(5.0, no_retries))
    assert len(mock_urllib3.requests) == 2
    assert mock_urllib3.requests[-1].timeout == (1.0, 5.0)

    with pytest.raises(requests.ConnectionError):
        session.get('http://name/foo', timeout=(2.0, 5.0, no_retries))
    assert len(mock_urllib3.requests) == 3
    assert mock_urllib3.requests[-1].timeout == (2.0, 5.0)


def test_adapter_bad_timeout_raises():
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter()
    session.mount('http://name', adapter)

    with pytest.raises(ValueError):
        session.get('http://name/foo', timeout="string")
    with pytest.raises(ValueError):
        session.get('http://name/foo', timeout=(1, 2, 3, 4))
    with pytest.raises(ValueError):
        session.get('http://name/foo', timeout=(1, 2, 3))


def test_adapter_callsite_retries(mock_urllib3):
    session = requests.Session()
    adapter = talisker.requests.TaliskerAdapter(
        ['1.2.3.4:8000', '1.2.3.4:8001', '4.3.2.1:8000'],
    )
    session.mount('http://name', adapter)

    mock_urllib3.set_error(socket.error())

    with pytest.raises(requests.ConnectionError):
        session.get('http://name/foo')

    assert mock_urllib3.call_list == [
        ('http://1.2.3.4:8000/foo', (1.0, 10.0)),
    ]

    with pytest.raises(requests.exceptions.ConnectionError):
        retry = urllib3.Retry(3, backoff_factor=1)
        session.get('http://name/foo', timeout=retry)

    assert mock_urllib3.call_list[1:] == [
        ('http://1.2.3.4:8001/foo', (1.0, 10.0)),
        ('http://4.3.2.1:8000/foo', (1.0, 9.0)),
        ('http://1.2.3.4:8000/foo', (1.0, 6.0)),
        ('http://1.2.3.4:8001/foo', (1.0, 1.0)),
    ]
