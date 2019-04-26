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

import json
import sys
import time
import wsgiref.util

import pytest
from freezegun import freeze_time

from talisker import request_id, wsgi
from talisker.context import track_request_metric
import talisker.sentry


@pytest.fixture
def start_response():
    def mock_start_response(status, headers, exc_info=None):
        mock_start_response.status = status
        mock_start_response.exc_info = exc_info
        mock_start_response.headers = headers
        mock_start_response.body = body = []

        # this mimics expected WSGI server behaviour
        if exc_info and mock_start_response.headers_sent:
            raise exc_info[0].with_traceback(exc_info[1], exc_info[2])

        return lambda x: body.append(x)

    # this mimics WSGI server state
    mock_start_response.headers_sent = False

    return mock_start_response


def test_error_response_handler(wsgi_env):
    wsgi_env['REQUEST_ID'] = 'REQUESTID'
    wsgi_env['SENTRY_ID'] = 'SENTRYID'
    wsgi_env['HTTP_ACCEPT'] = 'application/json'
    headers = [('X-VCS-Revision', 'revid')]
    exc_info = None

    try:
        raise Exception('test')
    except Exception:
        exc_info = sys.exc_info()

    content_type, body = wsgi.talisker_error_response(
        wsgi_env,
        headers,
        exc_info,
    )
    error = json.loads(body.decode('utf8'))
    assert content_type == 'application/json'
    assert error['title'] == 'Request REQUESTID: Exception'
    assert error['id'] == {
        'Request-Id': 'REQUESTID',
        'Sentry-ID': 'SENTRYID',
    }
    assert error['traceback'] == '[traceback hidden]'
    assert error['request_headers'] == {
        'Accept': 'application/json',
        'Host': '127.0.0.1',
    }
    assert error['wsgi_env']['REQUEST_ID'] == 'REQUESTID'
    assert error['wsgi_env']['SENTRY_ID'] == 'SENTRYID'
    assert error['response_headers'] == {
        'X-VCS-Revision': 'revid',
    }


def test_error_response_handler_devel(wsgi_env, config):
    config['DEVEL'] = '1'
    wsgi_env['REQUEST_ID'] = 'REQUESTID'
    wsgi_env['SENTRY_ID'] = 'SENTRYID'
    wsgi_env['HTTP_ACCEPT'] = 'application/json'
    headers = [('X-VCS-Revision', 'revid')]
    exc_info = None

    try:
        raise Exception('test')
    except Exception:
        exc_info = sys.exc_info()

    content_type, body = wsgi.talisker_error_response(
        wsgi_env,
        headers,
        exc_info,
    )
    error = json.loads(body.decode('utf8'))
    assert error['title'] == 'Request REQUESTID: test'
    assert error['traceback'][0] == 'Traceback (most recent call last):'
    assert error['traceback'][-3] == '    raise Exception(\'test\')'
    assert error['traceback'][-2] == 'Exception: test'


def test_wsgi_response_start_response(wsgi_env, start_response):
    wsgi_env['REQUEST_ID'] = 'ID'
    headers = {'HEADER': 'VALUE'}
    response = wsgi.WSGIResponse(wsgi_env, start_response, headers)
    response.start_response('200 OK', [], None)
    response.call_start_response()
    assert response.status_code == 200
    assert start_response.status == response.status == '200 OK'
    assert start_response.headers == response.headers == [
        ('HEADER', 'VALUE'),
        ('X-Request-Id', 'ID'),
    ]
    assert start_response.exc_info is response.exc_info is None


def test_wsgi_response_soft_timeout_default(wsgi_env, start_response, context):
    with freeze_time() as frozen:
        wsgi_env['start_time'] = time.time()
        response = wsgi.WSGIResponse(wsgi_env, start_response, [])
        frozen.tick(100)
        response.start_response('200 OK', [], None)
        list(response.wrap([b'']))

    assert context.sentry == []


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_wsgi_response_soft_explicit(wsgi_env, start_response, context):
    with freeze_time() as frozen:
        wsgi_env['start_time'] = time.time()
        response = wsgi.WSGIResponse(wsgi_env, start_response, [], 100)
        frozen.tick(2.0)
        response.start_response('200 OK', [], None)
        list(response.wrap([b'']))

    assert (
        context.sentry[0]['message'] == 'Start_response over timeout: 100ms'
    )
    assert context.sentry[0]['level'] == 'warning'


@freeze_time('2016-01-02 03:04:05.1234')
def test_wsgi_response_wrap(wsgi_env, start_response, context):
    wsgi_env['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(wsgi_env, start_response)
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
    wsgi_env['start_time'] = time.time() - 1.0
    wsgi_env['wsgi.file_wrapper'] = wsgiref.util.FileWrapper

    response = wsgi.WSGIResponse(wsgi_env, start_response)
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
    wsgi_env['start_time'] = time.time() - 1.0
    wsgi_env['REQUEST_ID'] = 'REQUESTID'
    wsgi_env['HTTP_ACCEPT'] = 'application/json'
    response = wsgi.WSGIResponse(wsgi_env, start_response)
    response.start_response('200 OK', [], None)

    class ErrorGenerator():
        def __iter__(self):
            return self

        def __next__(self):
            raise Exception('error')

    output = b''.join(response.wrap(ErrorGenerator()))
    error = json.loads(output.decode('utf8'))

    assert error['title'] == 'Request REQUESTID: Exception'

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
    wsgi_env['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(wsgi_env, start_response)
    response.start_response('200 OK', [], None)

    def iterator():
        start_response.headers_sent = True
        yield b'some content'
        raise Exception('error')

    it = response.wrap(iterator())
    with pytest.raises(Exception):
        list(it)


@freeze_time()
def test_wsgi_response_wrap_no_body(
        wsgi_env, start_response, context):
    wsgi_env['start_time'] = time.time() - 1.0
    response = wsgi.WSGIResponse(wsgi_env, start_response)
    response.start_response('304 Not Modified', [], None)

    def iterator():
        return []

    output = b''.join(response.wrap(iterator()))
    assert output == b''
    assert start_response.headers == []
    assert start_response.status == '304 Not Modified'


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
    wsgi_env['HTTP_ACCEPT'] = 'application/json'

    mw = wsgi.TaliskerMiddleware(app, extra_env, extra_headers)
    output = b''.join(mw(wsgi_env, start_response))
    error = json.loads(output.decode('utf8'))

    assert error['title'] == 'Request ID: Exception'
    assert wsgi_env['ENV'] == 'VALUE'
    assert wsgi_env['REQUEST_ID'] == 'ID'
    assert start_response.status == '500 Internal Server Error'
    assert start_response.exc_info[0] is Exception
    assert start_response.headers[:3] == [
        ('Content-Type', 'application/json'),
        ('Some-Header', 'value'),
        ('X-Request-Id', 'ID'),
    ]
    if talisker.sentry.enabled:
        assert start_response.headers[3] == (
            'X-Sentry-ID', wsgi_env['SENTRY_ID']
        )

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

    def app(wsgi_env, _start_response):
        _start_response('200 OK', [('Content-Type', 'application/json')])
        raise Exception('error')

    extra_env = {'ENV': 'VALUE'}
    extra_headers = {'Some-Header': 'value'}
    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'
    wsgi_env['HTTP_ACCEPT'] = 'application/json'

    mw = wsgi.TaliskerMiddleware(app, extra_env, extra_headers)
    output = b''.join(mw(wsgi_env, start_response))
    error = json.loads(output.decode('utf8'))

    assert error['title'] == 'Request ID: Exception'
    assert wsgi_env['ENV'] == 'VALUE'
    assert wsgi_env['REQUEST_ID'] == 'ID'
    assert start_response.status == '500 Internal Server Error'
    assert start_response.headers[:3] == [
        ('Content-Type', 'application/json'),
        ('Some-Header', 'value'),
        ('X-Request-Id', 'ID'),
    ]
    if talisker.sentry.enabled:
        assert start_response.headers[3] == (
            'X-Sentry-ID', wsgi_env['SENTRY_ID']
        )

    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra={
            'status': 500,
            'exc_type': 'Exception',
        },
    )


def test_middleware_preserves_file_wrapper(
        wsgi_env, start_response, context, tmpdir):
    path = tmpdir.join('filecontent')
    path.write('CONTENT')

    def app(environ, _start_response):
        _start_response('200 OK', [('Content-Type', 'text/plain')])
        return environ['wsgi.file_wrapper'](open(str(path)))

    mw = wsgi.TaliskerMiddleware(app, {}, {})
    wsgi_env['wsgi.file_wrapper'] = wsgiref.util.FileWrapper

    with freeze_time() as frozen:
        respiter = mw(wsgi_env, start_response)
        context.assert_not_log(msg='GET /')
        frozen.tick(1.0)
        respiter.close()

    assert isinstance(respiter, wsgiref.util.FileWrapper)
    context.assert_log(
        msg='GET /',
        extra=dict([
            ('method', 'GET'),
            ('path', '/'),
            ('status', 200),
            ('duration_ms', 1000.0),
            ('ip', '127.0.0.1'),
            ('proto', 'HTTP/1.0'),
            ('length', len('CONTENT')),
            ('filepath', str(path)),
        ]),
    )


def test_middleware_debug_middleware_error(wsgi_env, start_response, context):
    from werkzeug.debug import DebuggedApplication

    def app(environ, _):
        raise Exception('error')

    mw = wsgi.TaliskerMiddleware(DebuggedApplication(app), {}, {})

    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'
    list(mw(wsgi_env, start_response))

    assert start_response.status == '500 INTERNAL SERVER ERROR'
    assert start_response.headers == [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('X-XSS-Protection', '0'),
        ('X-Request-Id', 'ID'),
    ]

    context.assert_log(name='talisker.wsgi', msg='GET /')


def test_middleware_debug_middleware(wsgi_env, start_response, context):
    from werkzeug.debug import DebuggedApplication

    # DebuggedApplication turns any WSGI app into a super lazy version
    def app(environ, start_response):
        start_response('302 Found', [('Location', '/other')])
        yield b''

    mw = wsgi.TaliskerMiddleware(DebuggedApplication(app), {}, {})

    wsgi_env['HTTP_X_REQUEST_ID'] = 'ID'
    output = b''.join(mw(wsgi_env, start_response))

    assert start_response.status == '302 Found'
    assert output == b''
    assert start_response.headers == [
        ('Location', '/other'),
        ('X-Request-Id', 'ID'),
    ]


def test_middleware_debug_middleware_no_content(
        wsgi_env, start_response, context):
    from werkzeug.debug import DebuggedApplication

    # DebuggedApplication turns any WSGI app into a super lazy version
    def app(environ, start_response):
        start_response('304 Not Modified', [])
        # no content
        return []

    mw = wsgi.TaliskerMiddleware(DebuggedApplication(app), {}, {})

    output = b''.join(mw(wsgi_env, start_response))

    assert start_response.status == '304 Not Modified'
    assert output == b''


def test_get_metadata_basic(wsgi_env):
    msg, extra = wsgi.get_metadata(
        wsgi_env,
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
    wsgi_env['PATH_INFO'] = '/foo'
    wsgi_env['QUERY_STRING'] = 'bar=baz'
    msg, extra = wsgi.get_metadata(
        wsgi_env,
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
    msg, extra = wsgi.get_metadata(
        wsgi_env,
        status=200,
        headers=[('X-View-Name', 'view')],
        duration=1,
        length=1000,
    )
    assert extra['view'] == 'view'


def test_get_metadata_forwarded(wsgi_env):
    wsgi_env['HTTP_X_FORWARDED_FOR'] = '203.0.113.195, 150.172.238.178'
    msg, extra = wsgi.get_metadata(
        wsgi_env,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['forwarded'] == '203.0.113.195, 150.172.238.178'


def test_get_metadata_request_body(wsgi_env):
    wsgi_env['CONTENT_LENGTH'] = '100'
    wsgi_env['CONTENT_TYPE'] = 'application/json'
    msg, extra = wsgi.get_metadata(
        wsgi_env,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['request_length'] == 100
    assert extra['request_type'] == 'application/json'


def test_get_metadata_referrer(wsgi_env):
    wsgi_env['HTTP_REFERER'] = 'referrer'
    msg, extra = wsgi.get_metadata(
        wsgi_env,
        status=200,
        headers=[],
        duration=1,
        length=1000,
    )
    assert extra['referrer'] == 'referrer'


def test_get_metadata_ua(wsgi_env):
    wsgi_env['HTTP_USER_AGENT'] = 'ua'
    msg, extra = wsgi.get_metadata(
        wsgi_env,
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
    msg, extra = wsgi.get_metadata(
        wsgi_env,
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
    with request_id.context('ID'):
        wsgi.log_response(
            wsgi_env,
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
    wsgi.log_response(
        wsgi_env,
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

    assert context.statsd[0] == 'wsgi.requests.view.GET.500:1|c'
    assert context.statsd[1] == 'wsgi.latency.view.GET.500:1000.000000|ms'
    assert context.statsd[2] == 'wsgi.errors.view.GET.500:1|c'


def test_log_response_timeout(wsgi_env, context):
    wsgi_env['VIEW_NAME'] = 'view'
    wsgi.log_response(
        wsgi_env,
        duration=1,
        timeout=True,
    )
    extra = dict([
        ('method', 'GET'),
        ('path', '/'),
        ('duration_ms', 1000.0),
        ('ip', '127.0.0.1'),
        ('proto', 'HTTP/1.0'),
        ('timeout', True),
    ])
    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra=extra,
    )

    assert context.statsd[0] == 'wsgi.requests.view.GET.none:1|c'
    assert context.statsd[1] == 'wsgi.latency.view.GET.none:1000.000000|ms'
    assert context.statsd[2] == 'wsgi.timeouts.view.GET:1|c'


def test_log_response_raises(wsgi_env, context, monkeypatch):

    def error(*args, **kwargs):
        raise Exception('error')

    monkeypatch.setattr(wsgi, 'get_metadata', error)

    wsgi.log_response(
        wsgi_env,
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

    def app(environ, start_response):
        start_response(200, [])
        return environ

    wrapped = wsgi.wrap(app)

    assert wrapped._talisker_wrapped is True
    assert wrapped._talisker_original_app is app
    assert wrapped is not app

    wrapped2 = wsgi.wrap(wrapped)
    assert wrapped2 is wrapped
