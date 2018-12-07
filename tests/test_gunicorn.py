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

import datetime
import itertools
import json
import logging
import os
import signal
import subprocess
import sys
import time

from gunicorn.config import Config
import requests

from talisker import gunicorn
from talisker import logs
from talisker import request_id
from talisker import statsd
from talisker.testing import GunicornProcess
from talisker.context import track_request_metric

from tests.test_metrics import counter_name


def test_talisker_entrypoint():
    entrypoint = 'talisker.gunicorn'
    subprocess.check_output([entrypoint, '--help'])


def test_gunicorn_logger_set_formatter_on_access_log():
    cfg = Config()
    cfg.set('accesslog', '/tmp/log')
    logger = gunicorn.GunicornLogger(cfg)
    access = logger._get_gunicorn_handler(logger.access_log)
    assert isinstance(access.formatter, logs.StructuredFormatter)


def test_gunicorn_logger_no_handler_for_stderr_access_log():
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    assert logger.access_log.propagate is True
    assert logger._get_gunicorn_handler(logger.access_log) is None


def test_gunicorn_logger_propagate_error_log():
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)
    assert logger.error_log.propagate is True
    assert len(logger.error_log.handlers) == 0


class MockResponse:
    status_code = 200
    status = '200 OK'
    sent = 1000

    def __init__(self):
        self.headers = []


def access_extra_args(environ, url='/'):
    response = MockResponse()
    response.headers.append(('X-View-Name', 'view'))
    delta = datetime.timedelta(seconds=1)
    parts = url.split('?')
    path = parts[0]
    qs = parts[1] if len(parts) > 1 else ''
    environ['RAW_URI'] = url
    environ['HTTP_X_FORWARDED_FOR'] = '203.0.113.195, 150.172.238.178'
    environ['QUERY_STRING'] = qs
    environ['PATH_INFO'] = path
    environ['REMOTE_ADDR'] = '127.0.0.1'
    environ['HTTP_REFERER'] = 'referrer'
    environ['HTTP_USER_AGENT'] = 'ua'
    expected = dict()
    expected['method'] = 'GET'
    expected['path'] = path
    expected['qs'] = qs
    expected['status'] = 200
    expected['view'] = 'view'
    expected['duration_ms'] = 1000.0
    expected['ip'] = '127.0.0.1'
    expected['proto'] = 'HTTP/1.0'
    expected['length'] = 1000
    expected['referrer'] = 'referrer'
    expected['forwarded'] = '203.0.113.195, 150.172.238.178'
    expected['ua'] = 'ua'
    return response, environ, delta, expected


def test_gunicorn_get_response_status():
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)

    class Response1:
        status_code = 200
    assert logger.get_response_status(Response1()) == 200

    class Response2:
        status = '200 OK'
    assert logger.get_response_status(Response2()) == 200

    class Response3:
        status = 200
    assert logger.get_response_status(Response3()) == 200


def test_gunicorn_logger_get_extra(wsgi_env):
    track_request_metric('sql', 1.0)
    track_request_metric('http', 2.0)
    track_request_metric('log', 3.0)
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/foo?bar=baz')
    expected['sql_count'] = 1
    expected['sql_time_ms'] = 1.0
    expected['http_count'] = 1
    expected['http_time_ms'] = 2.0
    expected['log_count'] = 1
    expected['log_time_ms'] = 3.0
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)
    msg, extra = logger.get_extra(response, None, environ, delta, 200)
    assert msg == 'GET /foo?'
    assert extra == expected


def test_gunicorn_logger_access(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /', extra=expected)
    assert context.statsd[0] == 'gunicorn.count.view.GET.200:1|c'
    assert context.statsd[1].startswith('gunicorn.latency.view.GET.200:')


def test_gunicorn_logger_access_500(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    response.status_code = 500
    response.status = '500 Server Error'
    expected['status'] = 500
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /', extra=expected)
    assert context.statsd[0] == 'gunicorn.count.view.GET.500:1|c'
    assert context.statsd[1] == 'gunicorn.errors.view.GET.500:1|c'
    assert context.statsd[2].startswith('gunicorn.latency.view.GET.500:')


def test_gunicorn_logger_access_no_view(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    response.headers = []
    expected.pop('view')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /', extra=expected)
    assert context.statsd[0] == 'gunicorn.count.unknown.GET.200:1|c'
    assert context.statsd[1].startswith('gunicorn.latency.unknown.GET.200:')


def test_gunicorn_logger_access_no_forwarded(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    environ.pop('HTTP_X_FORWARDED_FOR')
    response.headers = [('X-View-Name', 'view')]
    expected.pop('forwarded')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /', extra=expected)
    assert context.statsd[0] == 'gunicorn.count.view.GET.200:1|c'
    assert context.statsd[1].startswith('gunicorn.latency.view.GET.200:')


def test_gunicorn_logger_access_forwarded(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /', extra=expected)
    assert context.statsd[0] == 'gunicorn.count.view.GET.200:1|c'
    assert context.statsd[1].startswith('gunicorn.latency.view.GET.200:')


def test_gunicorn_logger_access_qs(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/url?foo=bar')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)

    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(msg='GET /url?', extra=expected)


def test_gunicorn_logger_access_with_request_id(wsgi_env, context):
    rid = 'request-id'
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    expected['request_id'] = rid
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)

    context.logs[:] = []
    with request_id.context(rid):
        logger.access(response, None, environ, delta)
    context.assert_log(extra=expected)


def test_gunicorn_logger_access_with_request_content(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/')
    environ['CONTENT_TYPE'] = 'type'
    environ['CONTENT_LENGTH'] = '10'
    expected['request_type'] = 'type'
    expected['request_length'] = 10
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)

    context.logs[:] = []
    logger.access(response, None, environ, delta)
    context.assert_log(extra=expected)


def test_gunicorn_logger_status_url(wsgi_env, context):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/_status/ping')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    statsd.get_client()  # force the statsd creationg log message
    context.logs[:] = []
    logger.access(response, None, environ, delta)
    assert len(context.logs) == 0
    assert len(context.statsd) == 0


def test_gunicorn_logger_status_url_enabled(
        wsgi_env, context, monkeypatch, config):
    response, environ, delta, expected = access_extra_args(
        wsgi_env, '/_status/ping')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    statsd.get_client()  # force the statsd creationg log message
    context.logs[:] = []
    config['TALISKER_LOGSTATUS'] = 'true'
    logger.access(response, None, environ, delta)
    assert len(context.logs) == 1
    assert len(context.statsd) == 0


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.logger_class == gunicorn.GunicornLogger
    assert app.cfg.loglevel.lower() == 'info'
    assert app.cfg.pre_request is gunicorn.gunicorn_pre_request
    assert app.cfg.on_starting is gunicorn.gunicorn_on_starting
    assert app.cfg.child_exit is gunicorn.gunicorn_child_exit
    assert logs.get_talisker_handler().level == logging.NOTSET


def test_gunicorn_application_init_devel(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.accesslog == '-'
    assert app.cfg.timeout == 99999
    assert app.cfg.reload


def test_gunicorn_application_init_devel_overriden(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--timeout', '10'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.timeout == 10


def test_gunicorn_application_config_errorlog(monkeypatch, context):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--log-file', '/tmp/log'])
    app = gunicorn.TaliskerApplication('')
    context.assert_log(
        msg='ignoring gunicorn errorlog',
        extra={'errorlog': '/tmp/log'},
    )
    assert app.cfg.errorlog == '-'


def test_gunicorn_application_config_loglevel_debug_devel(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--log-level', 'debug'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.loglevel.lower() == 'debug'
    assert logs.get_talisker_handler().level == logging.DEBUG


def test_gunicorn_application_config_statsd(monkeypatch, context):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--statsd-host', 'localhost:8125'])
    app = gunicorn.TaliskerApplication('')
    context.assert_log(
        msg='ignoring gunicorn statsd',
        extra={'statsd_host': ('localhost', 8125)},
    )
    assert app.cfg.statsd_host is None
    assert app.cfg.statsd_prefix is None


def test_gunicorn_application_config_logger_class(monkeypatch, context):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--logger-class', 'gunicorn.glogging.Logger'])
    from gunicorn.glogging import Logger
    app = gunicorn.TaliskerApplication('')
    context.assert_log(
        msg='using custom gunicorn logger class',
        extra={'logger_class': Logger},
    )
    assert app.cfg.logger_class is Logger


def wsgi(environ, start_response):
    start_response('200 OK', [])
    return ''


def test_gunicorn_application_load(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv', ['', __name__ + ':wsgi', '--bind=0.0.0.0:0'])
    app = gunicorn.TaliskerApplication('')
    wsgiapp = app.load_wsgiapp()
    assert wsgiapp._talisker_wrapped
    assert wsgiapp._talisker_original_app == wsgi


counter = itertools.count()
next(counter)


def counter_app(environ, start_response, accumulator=[]):
    start_response('200 OK', [('Content-Type', 'application/json')])
    num = str(next(counter))
    logs.logging_context.push({num: num})
    return [json.dumps(logs.logging_context.flat).encode('utf8')]


def test_gunicorn_clears_context():
    app = __name__ + ':counter_app'
    pr = GunicornProcess(app, args=['--worker-class=sync'])
    with pr:
        r1 = requests.get(pr.url('/')).json()
        r2 = requests.get(pr.url('/')).json()
        r3 = requests.get(pr.url('/')).json()

    assert r1['1'] == '1'
    assert r2['2'] == '2'
    assert '1' not in r2
    assert r3['3'] == '3'
    assert '2' not in r3


def test_gunicorn_prometheus_cleanup(caplog):
    caplog.set_level(logging.INFO)
    app = __name__ + ':counter_app'
    workers = 8
    server = GunicornProcess(
        app, args=['--worker-class=sync', '-w', str(workers)])

    def increment(n):
        for i in range(n):
            requests.get(server.url('/_status/test/prometheus'))

    def files(pid):
        pid = str(pid)
        pid_files = set()
        archives = set()
        for path in os.listdir(os.environ['prometheus_multiproc_dir']):
            # ignore master pids
            if pid in path:
                continue
            if '_archive.db' in path:
                archives.add(path)
            else:
                pid_files.add(path)
        return archives, pid_files

    def stats():
        return requests.get(server.url('/_status/metrics')).text

    name = counter_name('test_total')
    valid_archives = set(['counter_archive.db', 'histogram_archive.db'])
    with server:
        # forking can be really slow on travis, so make sure *all* the workers
        # have had time to spin up before running the test
        if os.environ.get('CI') == 'true':
            time.sleep(10.0)
        increment(1000)
        archives, pid_files_1 = files(server.ps.pid)
        assert len(archives) == 0
        # different number of files depending on prometheus_client version
        # so we assert against 1x or 2x workers
        assert len(pid_files_1) in (workers, 2 * workers)
        assert name + ' 1000.0' in stats()

        os.kill(server.ps.pid, signal.SIGHUP)
        time.sleep(2.0)

        archives, pid_files_2 = files(server.ps.pid)
        assert archives == valid_archives
        assert pid_files_1.isdisjoint(pid_files_2)
        assert name + ' 1000.0' in stats()

        increment(1000)
        assert name + ' 2000.0' in stats()
        archives, pid_files_3 = files(server.ps.pid)
        assert archives == valid_archives
        assert len(pid_files_3) in (workers, 2 * workers)

        os.kill(server.ps.pid, signal.SIGHUP)
        time.sleep(2.0)

        archives, pid_files_4 = files(server.ps.pid)
        assert archives == valid_archives
        assert pid_files_3.isdisjoint(pid_files_4)
        assert name + ' 2000.0' in stats()
