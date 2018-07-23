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

import pytest
import raven.context
import requests
import responses
from werkzeug.local import release_local

import talisker.requests
import talisker.statsd


def request(method='GET', host='http://example.com', url='/', **kwargs):
    req = requests.Request(method, url=host + url, **kwargs)
    return req.prepare()


def response(
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


def test_collect_metadata_hostname(monkeypatch):
    monkeypatch.setitem(talisker.requests.HOSTS, '1.2.3.4', 'myhost.com')
    req = request(url='/foo/bar', host='http://1.2.3.4:8000')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://myhost.com:8000/foo/bar',
        'method': 'GET',
        'host': 'myhost.com',
        'ip': '1.2.3.4',
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
    resp = response(req, view='views.name', body=u'some content')
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


def test_metric_hook(statsd_metrics):
    r = response(view='view')

    with raven.context.Context() as ctx:
        talisker.requests.metrics_response_hook(r)

    assert statsd_metrics[0] == 'requests.count.example-com.view:1|c'
    assert statsd_metrics[1] == (
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


def test_metric_hook_user_name(statsd_metrics):
    r = response(view='view')

    with raven.context.Context() as ctx:
        talisker.requests._local.metric_api_name = 'api'
        talisker.requests._local.metric_host_name = 'service'
        talisker.requests.metrics_response_hook(r)
        release_local(talisker.requests._local)

    assert statsd_metrics[0] == 'requests.count.service.api:1|c'
    assert statsd_metrics[1] == (
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


@responses.activate
def test_configured_session(statsd_metrics):
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
    assert statsd_metrics[0] == 'requests.count.localhost.view:1|c'
    assert statsd_metrics[1].startswith(
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
def test_configured_session_http_error(statsd_metrics):
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

    assert statsd_metrics[0] == 'requests.count.localhost.view:1|c'
    assert statsd_metrics[1].startswith('requests.latency.localhost.view.500:')
    assert statsd_metrics[2] == (
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


def test_configured_session_connection_error(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    with raven.context.Context() as ctx:
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get('http://nope.nowhere/foo')

    assert statsd_metrics[0] == 'requests.count.nope-nowhere.unknown:1|c'
    assert statsd_metrics[1].startswith(
        'requests.errors.nope-nowhere.connection.unknown.')
    # error code depends on python version host dns set up
    assert any((
        statsd_metrics[1].endswith('unknown:1|c'),
        statsd_metrics[1].endswith('EAI_NONAME:1|c'),
        statsd_metrics[1].endswith('EAI_AGAIN:1|c'),
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
def test_configured_session_with_user_name(statsd_metrics):
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
    assert statsd_metrics[0].startswith('requests.count.service.api:')
    assert statsd_metrics[1].startswith('requests.latency.service.api.200:')
