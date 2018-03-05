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

from datetime import timedelta

import pytest
import raven.context
import requests
import responses

import talisker.requests
import talisker.statsd


def response(
        method='GET',
        host='http://example.com',
        url='/',
        code=200,
        elapsed=1.0):
    req = requests.Request(method, host + url)
    resp = requests.Response()
    resp.request = req.prepare()
    resp.status_code = code
    resp.elapsed = timedelta(seconds=elapsed)
    return resp


@pytest.mark.parametrize('resp, expected', [
    (response(), 'requests.example-com.GET.200'),
    (response(method='POST'), 'requests.example-com.POST.200'),
    (response(code=500), 'requests.example-com.GET.500'),
])
def test_get_metric_name_base(resp, expected):
    name = talisker.requests.get_metric_name(resp)
    assert name == expected


def test_get_metric_name_hostname(monkeypatch):
    monkeypatch.setitem(talisker.requests.HOSTS, '1.2.3.4', 'myhost.com')
    resp = response(host='http://1.2.3.4')
    name = talisker.requests.get_metric_name(resp)
    assert name == 'requests.myhost-com.GET.200'


def test_get_metric_name_path_len():
    resp = response(url='/foo/bar')
    name = talisker.requests.get_metric_name(resp, 2)
    assert name == 'requests.example-com.foo.bar.GET.200'


def test_metric_hook(statsd_metrics):
    r = response()

    with raven.context.Context() as ctx:
        talisker.requests.metrics_response_hook(r)

    assert statsd_metrics[0] == 'requests.example-com.GET.200:1000.000000|ms'
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://example.com/'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration'] == 1000.0


@responses.activate
def test_configured_session(statsd_metrics, ):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(responses.GET, 'http://localhost/foo/bar', body='OK')

    with talisker.request_id.context('XXX'):
        with raven.context.Context() as ctx:
            session.get('http://localhost/foo/bar')

    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[0].startswith('requests.localhost.GET.200:')
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://localhost/foo/bar'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert 'duration' in breadcrumbs[0]['data']


def test_configured_session_connection_error(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    with raven.context.Context() as ctx:
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get('http://nowhere/')

    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://nowhere/'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert 'ConnectionError' in breadcrumbs[0]['data']['exception']


@responses.activate
def test_configured_session_disable_metrics(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(responses.GET, 'http://localhost/foo/bar', body='OK')

    with talisker.request_id.context('XXX'):
        session.get('http://localhost/foo/bar', emit_metric=False)

    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert len(statsd_metrics) == 0


@responses.activate
def test_configured_session_with_url_metrics(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(responses.GET, 'http://localhost/foo/bar', body='OK')

    with talisker.request_id.context('XXX'):
        session.get('http://localhost/foo/bar', metric_path_len=1)
        session.get('http://localhost/foo/bar', metric_path_len=2)
        session.get('http://localhost/foo/bar')

    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[0].startswith('requests.localhost.foo.GET.200:')

    assert responses.calls[1].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[1].startswith('requests.localhost.foo.bar.GET.200:')

    assert responses.calls[2].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[2].startswith('requests.localhost.GET.200:')
