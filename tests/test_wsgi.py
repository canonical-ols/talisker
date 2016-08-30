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
    assert ('extra', 'header') in headers


def test_wrapping():
    wrapped = wsgi.wrap(app)

    assert wrapped._talisker_wrapped is True
    assert wrapped._talisker_original_app is app
    assert wrapped is not app

    wrapped2 = wsgi.wrap(wrapped)
    assert wrapped2 is wrapped
