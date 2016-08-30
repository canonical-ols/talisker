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
import requests
import pytest
import talisker.requests
import talisker.statsd


class Client(list):

    def timing(self, prefix, duration):
        self.append((prefix, duration))


@pytest.fixture
def statsd():
    try:
        talisker.statsd._client = Client()
        yield talisker.statsd._client
    finally:
        talisker.statsd._client = None


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


def test_get_timing_root():
    r = response()
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.GET.200'
    assert duration == 1000.0


def test_get_timing_post():
    r = response(method='POST')
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.POST.200'
    assert duration == 1000.0


def test_get_timing_500():
    r = response(code=500)
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.GET.500'
    assert duration == 1000.0


def test_metric_hook(statsd):
    r = response()
    talisker.requests.metrics_response_hook(r)
    assert statsd[0] == ('requests.example-com.GET.200', 1000.0)


def test_configure():
    session = requests.Session()
    talisker.requests.configure(session)

    req = requests.Request('GET', 'http://localhost')
    with talisker.request_id.context('XXX'):
        prepared = session.prepare_request(req)

    assert prepared.headers['X-Request-Id'] == 'XXX'
