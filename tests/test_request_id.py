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

from py.test import fixture

from tests.conftest import run_wsgi  # noqa

from talisker import request_id
from talisker.request_context import request_context


@fixture
def id():
    return request_id.generate()


def app(environ, start_response):
    start_response(200, [])
    return [
        environ.get('REQUEST_ID'),
        request_id.get(),
        request_context.extra['request_id'],
    ]


REQUEST_ID = 'X-Request-Id'


def test_middleware_with_id(environ, id):
    middleware = request_id.RequestIdMiddleware(app)
    environ['HTTP_X_REQUEST_ID'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert ('X-Request-Id', id) in headers


def test_middleware_without_id(environ, id, monkeypatch):
    monkeypatch.setattr(request_id, 'generate', lambda: id)
    middleware = request_id.RequestIdMiddleware(app)
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert ('X-Request-Id', id) in headers


def test_middleware_alt_header(environ, id):
    middleware = request_id.RequestIdMiddleware(app, 'X-Alternate')
    environ['HTTP_X_ALTERNATE'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert ('X-Alternate', id) in headers


def test_decorator(id):

    @request_id.decorator(lambda: id)
    def test():
        assert request_id.get() == id

    assert request_id.get() is None
    test()
    assert request_id.get() is None


def test_context(id):
    assert request_id.get() is None
    with request_id.context(id):
        assert request_id.get() == id
    assert request_id.get() is None


def test_context_existing_id(id):
    request_id.set('existing')
    assert request_id.get() == 'existing'
    with request_id.context(id):
        assert request_id.get() == id
    assert request_id.get() == 'existing'
