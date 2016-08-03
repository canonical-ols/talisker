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
import talisker.requests


# @pytest.fixture
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


def test_metric_hook_root():
    r = response()
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.GET.200'
    assert duration == 1000.0


def test_metric_hook_post():
    r = response(method='POST')
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.POST.200'
    assert duration == 1000.0


def test_metric_hook_500():
    r = response(code=500)
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.GET.500'
    assert duration == 1000.0
