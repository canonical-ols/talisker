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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from talisker.testing import run_wsgi
from talisker import wsgi


def app(environ, start_response):
    start_response(200, [])
    return environ


def test_set_environ(wsgi_env):
    stack = wsgi.set_environ(app, X=1)
    env, status, headers = run_wsgi(stack, wsgi_env)
    assert env['X'] == 1


def test_set_headers(wsgi_env):
    stack = wsgi.set_headers(app, {'extra': 'header'})
    env, status, headers = run_wsgi(stack, wsgi_env)
    assert ('extra', 'header') in headers


def test_set_headers_overwrites(wsgi_env):
    def proxy(environ, start_response):
        start_response(200, [('extra', 'foo')])
        return 'ok'
    stack = wsgi.set_headers(app, {'extra': 'header'})
    env, status, headers = run_wsgi(stack, wsgi_env)
    assert ('extra', 'header') in headers
    assert ('extra', 'foo') not in headers


def test_wrapping():
    wrapped = wsgi.wrap(app)

    assert wrapped._talisker_wrapped is True
    assert wrapped._talisker_original_app is app
    assert wrapped is not app

    wrapped2 = wsgi.wrap(wrapped)
    assert wrapped2 is wrapped
