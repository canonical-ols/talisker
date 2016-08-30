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

import uuid

from py.test import fixture
import mock

from .conftest import run_wsgi # noqa

from talisker import request_id
from talisker.request_context import request_context


@fixture
def id():
    return str(uuid.uuid4())


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
    environ[b'HTTP_X_REQUEST_ID'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert ('X-Request-Id', id) in headers


def test_middleware_without_id(environ, id):
    middleware = request_id.RequestIdMiddleware(app)
    with mock.patch('talisker.request_id.generate') as mock_id:
        mock_id.return_value = id
        body, status, headers = run_wsgi(middleware, environ)
        assert list(set(body)) == [id]
        assert ('X-Request-Id', id) in headers


def test_middleware_alt_header(environ, id):
    middleware = request_id.RequestIdMiddleware(app, 'X-Alternate')
    environ[b'HTTP_X_ALTERNATE'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert ('X-Alternate', id) in headers


def test_decorator(id):

    @request_id.decorator(lambda: id)
    def test():
        assert request_id.get() == id

    test()
