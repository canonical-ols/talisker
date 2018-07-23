##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from .conftest import run_wsgi # noqa

from talisker import wsgi


def app(environ, start_response):
    start_response(200, [])
    return environ


def test_set_environ(environ):
    stack = wsgi.set_environ(app, X=1)
    env, status, headers = run_wsgi(stack, environ)
    assert env['X'] == 1


def test_set_headers(environ):
    stack = wsgi.set_headers(app, {'extra': 'header'})
    env, status, headers = run_wsgi(stack, environ)
    assert headers['extra'] == 'header'


def test_set_headers_overwrites(environ):
    def proxy(environ, start_response):
        start_response(200, [('extra', 'foo')])
        return 'ok'
    stack = wsgi.set_headers(app, {'extra': 'header'})
    env, status, headers = run_wsgi(stack, environ)
    assert headers['extra'] == 'header'


def test_wrapping():
    wrapped = wsgi.wrap(app)

    assert wrapped._talisker_wrapped is True
    assert wrapped._talisker_original_app is app
    assert wrapped is not app

    wrapped2 = wsgi.wrap(wrapped)
    assert wrapped2 is wrapped
