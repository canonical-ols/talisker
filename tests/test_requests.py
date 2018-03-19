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
from io import StringIO
import sys

import pytest
import raven.context
import requests
import responses
from werkzeug.local import release_local

import talisker.requests
import talisker.statsd


def request(method='GET',
            host='http://example.com',
            url='/',
            **kwargs
            ):
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


@pytest.mark.parametrize('resp, expected', [
    (response(), 'example-com.GET.200'),
    (response(request(method='POST')), 'example-com.POST.200'),
    (response(code=500), 'example-com.GET.500'),
    (response(view='view.name'), 'example-com.view.name.GET.200'),
])
def test_get_metric_name_base(resp, expected):
    metadata = talisker.requests.collect_metadata(resp.request, resp)
    name = talisker.requests.get_metric_name(metadata)
    assert name == expected


def test_get_metric_name_hostname(monkeypatch):
    monkeypatch.setitem(talisker.requests.HOSTS, '1.2.3.4', 'myhost.com')
    resp = response(request(host='http://1.2.3.4'))
    metadata = talisker.requests.collect_metadata(resp.request, resp)
    name = talisker.requests.get_metric_name(metadata)
    assert name == 'myhost-com.GET.200'


def test_collect_metadata():
    req = request(url='/foo/bar')
    metadata = talisker.requests.collect_metadata(req, None)
    assert metadata == {
        'url': 'http://example.com/foo/bar',
        'method': 'GET',
        'host': 'example.com',
    }


def test_collect_metadata_request_body():
    req = request(method='POST', url='/foo/bar', json='"some data"')
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
        'duration': 1000,
        'response_type': 'text/plain',
        'response_size': 12,
    }


def test_metric_hook(statsd_metrics):
    r = response(view='view.name')

    with raven.context.Context() as ctx:
        talisker.requests.metrics_response_hook(r)

    assert statsd_metrics[0] == (
        'requests.example-com.view.name.GET.200:1000.000000|ms'
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://example.com/'
    assert breadcrumbs[0]['data']['host'] == 'example.com'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['view'] == 'view.name'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration'] == 1000.0


def test_metric_hook_user_name(statsd_metrics):
    r = response(view='view.name')

    with raven.context.Context() as ctx:
        name = 'foo.{host}.{status_code}'
        talisker.requests._local.user_metric_name = name
        talisker.requests.metrics_response_hook(r)
        release_local(talisker.requests._local)

    assert statsd_metrics[0] == 'requests.foo.example-com.200:1000.000000|ms'
    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://example.com/'
    assert breadcrumbs[0]['data']['host'] == 'example.com'
    assert breadcrumbs[0]['data']['view'] == 'view.name'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert breadcrumbs[0]['data']['duration'] == 1000.0


@responses.activate
def test_configured_session(statsd_metrics, ):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(
        responses.GET,
        'http://localhost/foo/bar',
        body='OK',
        headers={'X-View-Name': 'view.name'},
    )

    with talisker.request_id.context('XXX'):
        with raven.context.Context() as ctx:
            session.get('http://localhost/foo/bar')

    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[0].startswith(
        'requests.localhost.view.name.GET.200:',
    )
    breadcrumbs = ctx.breadcrumbs.get_buffer()

    assert breadcrumbs[0]['type'] == 'http'
    assert breadcrumbs[0]['category'] == 'requests'
    assert breadcrumbs[0]['data']['url'] == 'http://localhost/foo/bar'
    assert breadcrumbs[0]['data']['host'] == 'localhost'
    assert breadcrumbs[0]['data']['view'] == 'view.name'
    assert breadcrumbs[0]['data']['method'] == 'GET'
    assert breadcrumbs[0]['data']['status_code'] == 200
    assert 'duration' in breadcrumbs[0]['data']


def test_configured_session_connection_error(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    with raven.context.Context() as ctx:
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get('http://nowhere.nosuchtld/foo', )

    breadcrumbs = ctx.breadcrumbs.get_buffer()
    assert breadcrumbs[-1]['type'] == 'http'
    assert breadcrumbs[-1]['category'] == 'requests'
    assert breadcrumbs[-1]['data']['url'] == 'http://nowhere.nosuchtld/foo'
    assert breadcrumbs[-1]['data']['host'] == 'nowhere.nosuchtld'
    assert breadcrumbs[-1]['data']['method'] == 'GET'
    if sys.version_info[:2] >= (3, 3):
        # error code depends if we are running tests with network or not
        assert breadcrumbs[-1]['data']['errno'] in ('EAI_NONAME', 'EAI_AGAIN')


@responses.activate
def test_configured_session_with_user_name(statsd_metrics):
    session = requests.Session()
    talisker.requests.configure(session)

    responses.add(responses.GET, 'http://localhost/foo/bar', body='OK')

    with talisker.request_id.context('XXX'):
        session.get(
            'http://localhost/foo/bar',
            metric_name='foo.{host}.name.{status_code}',
        )

    assert responses.calls[0].request.headers['X-Request-Id'] == 'XXX'
    assert statsd_metrics[0].startswith('requests.foo.localhost.name.200:')
