#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from py.test import fixture

from tests.conftest import run_wsgi  # noqa

from talisker import request_id


@fixture
def id():
    return request_id.generate()


def app(environ, start_response):
    start_response(200, [])
    return [
        environ.get('REQUEST_ID'),
        request_id.get(),
    ]


REQUEST_ID = 'X-Request-Id'


def test_middleware_with_id(environ, id):
    middleware = request_id.RequestIdMiddleware(app)
    environ['HTTP_X_REQUEST_ID'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert headers['X-Request-Id'] == id


def test_middleware_without_id(environ, id, monkeypatch):
    monkeypatch.setattr(request_id, 'generate', lambda: id)
    middleware = request_id.RequestIdMiddleware(app)
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert headers['X-Request-Id'] == id


def test_middleware_alt_header(environ, id):
    middleware = request_id.RequestIdMiddleware(app, 'X-Alternate')
    environ['HTTP_X_ALTERNATE'] = id
    body, status, headers = run_wsgi(middleware, environ)
    assert list(set(body)) == [id]
    assert headers['X-Alternate'] == id


def test_middleware_overwrites_header(environ, id, monkeypatch):
    def proxy(environ, start_response):
        start_response(200, [('X-Request-Id', 'other-id')])
        return 'ok'

    monkeypatch.setattr(request_id, 'generate', lambda: id)
    middleware = request_id.RequestIdMiddleware(proxy)
    body, status, headers = run_wsgi(middleware, environ)
    assert headers['X-Request-Id'] == id


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
    request_id.push('existing')
    assert request_id.get() == 'existing'
    with request_id.context(id):
        assert request_id.get() == id
    assert request_id.get() == 'existing'


def test_push():
    assert request_id.get() is None
    request_id.push(None)
    assert request_id.get() is None
    request_id.push('id')
    assert request_id.get() == 'id'
    request_id.push(None)
    assert request_id.get() is None
