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

import time
import wsgiref.util

import pytest
from freezegun import freeze_time

from talisker import request_id, wsgi
from talisker.context import track_request_metric


def app(environ, start_response):
    start_response(200, [])
    return environ


def create_environ(environ, url):
    """Helper to creater a test WSGI environ."""
    parts = url.split('?')
    path = parts[0]
    qs = parts[1] if len(parts) > 1 else ''
    environ['RAW_URI'] = url
    if qs:
        environ['QUERY_STRING'] = qs
    environ['PATH_INFO'] = path
    environ['REMOTE_ADDR'] = '127.0.0.1'
    return environ


@pytest.fixture
def start_response():
    def mock_start_response(status, headers, exc_info=None):
        mock_start_response.status = status
        mock_start_response.exc_info = exc_info
        # gunicorn does this for multiple calls to start_response, but doesn't
        # actually sent them till the body is iterated
        mock_start_response.headers = headers
        mock_start_response.body = body = []

        # this mimics expected WSGI server behaviour
        if exc_info and mock_start_response.headers_sent:
            raise exc_info[0].with_traceback(exc_info[1], exc_info[2])
        return lambda x: body.append(x)

    mock_start_response.headers_sent = False

    return mock_start_response


def test_wsgi_response_start_response(wsgi_env, start_response):
    wsgi_env['REQUEST_ID'] = 'ID'
    environ = create_environ(wsgi_env, '/')
    headers = {'HEADER': 'VALUE'}
    response = wsgi.WSGIResponse(environ, start_response, headers)
    response.start_response('200 OK', [], None)
    response.ensure_start_response()
    assert response.status_code == 200
    assert start_response.status == response.status == '200 OK'
    assert start_response.headers == response.headers == [
        ('HEADER', 'VALUE'),
        ('X-Request-Id', 'ID'),
    ]
    assert start_response.exc_info is response.exc_info is None


@freeze_time('2016-01-02 03:04:05.1234')
def test_wsgi_response_wrap(wsgi_env, start_response, context):
    environ = create_environ(wsgi_env, '/')
    environ['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(environ, start_response)
    response.start_response('200 OK', [], None)
    output = b''.join(response.wrap([b'output', b' ', b'here']))

    assert output == b'output here'
    context.assert_log(
        msg='GET /',
        extra=dict([
            ('method', 'GET'),
            ('path', '/'),
            ('status', 200),
            ('duration_ms', 1000.0),
            ('ip', '127.0.0.1'),
            ('proto', 'HTTP/1.0'),
            ('length', len(output)),
        ]),
    )


@freeze_time('2016-01-02 03:04:05.1234')
def test_wsgi_response_wrap_file(wsgi_env, start_response, context, tmpdir):
    path = tmpdir.join('filecontent')
    path.write('CONTENT')
    environ = create_environ(wsgi_env, '/')
    environ['start_time'] = time.time() - 1.0
    environ['wsgi.file_wrapper'] = wsgiref.util.FileWrapper

    response = wsgi.WSGIResponse(environ, start_response)
    response.start_response('200 OK', [], None)
    wrapper = wsgiref.util.FileWrapper(open(str(path)))
    respiter = response.wrap(wrapper)
    output = ''.join(respiter)
    respiter.close()

    assert output == 'CONTENT'
    context.assert_log(
        msg='GET /',
        extra=dict([
            ('method', 'GET'),
            ('path', '/'),
            ('status', 200),
            ('duration_ms', 1000.0),
            ('ip', '127.0.0.1'),
            ('proto', 'HTTP/1.0'),
            ('length', len(output)),
            ('filepath', str(path)),
        ]),
    )


@freeze_time('2016-01-02 03:04:05.1234')
def test_wsgi_response_wrap_error(wsgi_env, start_response, context):
    environ = create_environ(wsgi_env, '/')
    environ['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(environ, start_response)
    response.start_response('200 OK', [], None)

    class ErrorGenerator():
        def __iter__(self):
            return self

        def __next__(self):
            raise Exception('error')

    output = b''.join(response.wrap(ErrorGenerator()))

    assert output == b'Exception'

    context.assert_log(
        msg='GET /',
        extra=dict([
            ('method', 'GET'),
            ('path', '/'),
            ('status', 500),
            ('duration_ms', 1000.0),
            ('ip', '127.0.0.1'),
            ('proto', 'HTTP/1.0'),
            ('length', len(output)),
            ('exc_type', 'Exception'),
        ]),
    )


@freeze_time('2016-01-02 03:04:05.1234')
def test_wsgi_response_wrap_error_headers_sent(
        wsgi_env, start_response, context):
    environ = create_environ(wsgi_env, '/')
    environ['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(environ, start_response)
    response.start_response('200 OK', [], None)

    def iterator():
        start_response.headers_sent = True
        yield b'some content'
        raise Exception('error')

    it = response.wrap(iterator())
    with pytest.raises(Exception):
        list(it)


def test_middleware_basic(wsgi_env, start_response, context):

    def app(environ, _start_response):
        _start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'OK']

    extra_env = {'ENV': 'VALUE'}
    extra_headers = {'Some-Header': 'value'}
    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'

    mw = wsgi.TaliskerMiddleware(app, extra_env, extra_headers)
    output = b''.join(mw(wsgi_env, start_response))

    assert output == b'OK'
    assert wsgi_env['ENV'] == 'VALUE'
    assert wsgi_env['REQUEST_ID'] == 'ID'
    assert start_response.status == '200 OK'
    assert start_response.headers == [
        ('Content-Type', 'text/plain'),
        ('Some-Header', 'value'),
        ('X-Request-Id', 'ID'),
    ]

    context.assert_log(name='talisker.wsgi', msg='GET /')


def test_middleware_error_before_start_response(
        wsgi_env, start_response, context):

    def app(environ, _start_response):
        raise Exception('error')

    extra_env = {'ENV': 'VALUE'}
    extra_headers = {'Some-Header': 'value'}
    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'

    mw = wsgi.TaliskerMiddleware(app, extra_env, extra_headers)
    output = b''.join(mw(wsgi_env, start_response))

    assert output == b'Exception'
    assert wsgi_env['ENV'] == 'VALUE'
    assert wsgi_env['REQUEST_ID'] == 'ID'
    assert start_response.status == '500 Internal Server Error'
    assert start_response.headers == [
        ('Content-Type', 'text/plain'),
        ('Some-Header', 'value'),
        ('X-Request-Id', 'ID'),
    ]
    assert start_response.exc_info[0] is Exception

    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra={
            'status': 500,
            'exc_type': 'Exception',
        },
    )


def test_middleware_error_after_start_response(
        wsgi_env, start_response, context):

    def app(environ, _start_response):
        _start_response('200 OK', [('Content-Type', 'application/json')])
        raise Exception('error')

    extra_env = {'ENV': 'VALUE'}
    extra_headers = {'Some-Header': 'value'}
    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'

    mw = wsgi.TaliskerMiddleware(app, extra_env, extra_headers)
    output = b''.join(mw(wsgi_env, start_response))

    assert output == b'Exception'
    assert wsgi_env['ENV'] == 'VALUE'
    assert wsgi_env['REQUEST_ID'] == 'ID'
    assert start_response.status == '500 Internal Server Error'
    assert start_response.headers == [
        ('Content-Type', 'text/plain'),
        ('Some-Header', 'value'),
        ('X-Request-Id', 'ID'),
    ]

    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra={
            'status': 500,
            'exc_type': 'Exception',
        },
    )


def test_get_metadata_basic(wsgi_env):
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert msg == 'GET /'
    assert list(extra.items()) == [
        ('method', 'GET'),
        ('path', '/'),
        ('status', 200),
        ('duration_ms', 1000.0),
        ('ip', '127.0.0.1'),
        ('proto', 'HTTP/1.0'),
        ('length', 1000),
    ]


def test_get_metadata_query_string(wsgi_env):
    environ = create_environ(wsgi_env, '/foo?bar=baz')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert msg == 'GET /foo?'
    assert list(extra.items()) == [
        ('method', 'GET'),
        ('path', '/foo'),
        ('qs', 'bar=baz'),
        ('status', 200),
        ('duration_ms', 1000.0),
        ('ip', '127.0.0.1'),
        ('proto', 'HTTP/1.0'),
        ('length', 1000),
    ]


def test_get_metadata_view(wsgi_env):
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[('X-View-Name', 'view')],
        duration=1,
        length=1000,
    )
    assert extra['view'] == 'view'


def test_get_metadata_forwarded(wsgi_env):
    wsgi_env['HTTP_X_FORWARDED_FOR'] = '203.0.113.195, 150.172.238.178'
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['forwarded'] == '203.0.113.195, 150.172.238.178'


def test_get_metadata_request_body(wsgi_env):
    wsgi_env['CONTENT_LENGTH'] = '100'
    wsgi_env['CONTENT_TYPE'] = 'application/json'
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['request_length'] == 100
    assert extra['request_type'] == 'application/json'


def test_get_metadata_referrer(wsgi_env):
    wsgi_env['HTTP_REFERER'] = 'referrer'
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['referrer'] == 'referrer'


def test_get_metadata_ua(wsgi_env):
    wsgi_env['HTTP_USER_AGENT'] = 'ua'
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['ua'] == 'ua'


def test_get_metadata_tracking(wsgi_env):
    track_request_metric('sql', 1.0)
    track_request_metric('http', 2.0)
    track_request_metric('log', 3.0)
    environ = create_environ(wsgi_env, '/')
    msg, extra = wsgi.get_metadata(
        environ,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['sql_count'] == 1
    assert extra['sql_time_ms'] == 1.0
    assert extra['http_count'] == 1
    assert extra['http_time_ms'] == 2.0
    assert extra['log_count'] == 1
    assert extra['log_time_ms'] == 3.0


def test_log_response(wsgi_env, context):
    environ = create_environ(wsgi_env, '/')
    with request_id.context('ID'):
        wsgi.log_response(
            environ,
            status=200,
            headers=[],
            duration=1,
            length=1000,
        )

    extra = dict([
        ('method', 'GET'),
        ('path', '/'),
        ('status', 200),
        ('duration_ms', 1000.0),
        ('ip', '127.0.0.1'),
        ('proto', 'HTTP/1.0'),
        ('length', 1000),
        ('request_id', 'ID'),
    ])
    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra=extra,
    )


def test_log_response_error(wsgi_env, context):
    environ = create_environ(wsgi_env, '/')
    wsgi.log_response(
        environ,
        status=500,
        headers=[('X-View-Name', 'view')],
        duration=1,
        length=1000,
    )
    extra = dict([
        ('method', 'GET'),
        ('path', '/'),
        ('status', 500),
        ('duration_ms', 1000.0),
        ('ip', '127.0.0.1'),
        ('proto', 'HTTP/1.0'),
        ('length', 1000),
    ])
    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra=extra,
    )

    assert context.statsd[0] == 'wsgi.count.view.GET.500:1|c'
    assert context.statsd[1] == 'wsgi.latency.view.GET.500:1000.000000|ms'
    assert context.statsd[2] == 'wsgi.errors.view.GET.500:1|c'


def test_log_response_raises(wsgi_env, context, monkeypatch):

    def error(*args, **kwargs):
        raise Exception('error')

    monkeypatch.setattr(wsgi, 'get_metadata', error)

    environ = create_environ(wsgi_env, '/')
    wsgi.log_response(
        environ,
        status=500,
        headers=[('X-View-Name', 'view')],
        duration=1,
        length=1000,
    )

    context.assert_log(
        name='talisker.wsgi',
        level='error',
        msg='error generating access log',
    )

    assert context.statsd == []


def test_wrap():
    wrapped = wsgi.wrap(app)

    assert wrapped._talisker_wrapped is True
    assert wrapped._talisker_original_app is app
    assert wrapped is not app

    wrapped2 = wsgi.wrap(wrapped)
    assert wrapped2 is wrapped
