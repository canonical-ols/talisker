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

import pytest

try:
    import gunicorn  # noqa
except ImportError:
    pytest.skip("skipping gunicorn only tests", allow_module_level=True)
else:
    del gunicorn

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
import pytest

from talisker import gunicorn  # noqa
from talisker.context import Context
from talisker import logs
from talisker.testing import GunicornProcess
import talisker.wsgi

from tests.test_metrics import counter_name


def test_talisker_entrypoint():
    entrypoint = 'talisker.gunicorn'
    subprocess.check_output([entrypoint, '--help'])


def test_gunicorn_logger_propagate_error_log():
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)
    assert logger.error_log.propagate is True
    assert len(logger.error_log.handlers) == 0


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.logger_class == gunicorn.GunicornLogger
    assert app.cfg.loglevel.lower() == 'info'
    assert app.cfg.on_starting is gunicorn.gunicorn_on_starting
    assert app.cfg.child_exit is gunicorn.gunicorn_child_exit
    assert app.cfg.worker_exit is gunicorn.gunicorn_worker_exit
    assert logs.get_talisker_handler().level == logging.NOTSET


def test_gunicorn_application_init_devel(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('', devel=True)
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


@pytest.mark.timeout(120)
@pytest.mark.flaky
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
    sleep_factor = 1
    if os.environ.get('CI') == 'true':
        # travis is slow
        sleep_factor = 10

    with server:
        # forking can be really slow on travis, so make sure *all* the workers
        # have had time to spin up before running the test
        time.sleep(1 * sleep_factor)
        increment(2000)
        archives, pid_files_1 = files(server.ps.pid)
        assert len(archives) == 0
        # different number of files depending on prometheus_client version
        # so we assert against 1x or 2x workers
        assert len(pid_files_1) in (workers, 2 * workers)
        assert name + ' 2000.0' in stats()

        os.kill(server.ps.pid, signal.SIGHUP)
        time.sleep(2 * sleep_factor)

        archives, pid_files_2 = files(server.ps.pid)
        assert archives == valid_archives
        assert pid_files_1.isdisjoint(pid_files_2)
        assert name + ' 2000.0' in stats()

        increment(2000)
        assert name + ' 4000.0' in stats()
        archives, pid_files_3 = files(server.ps.pid)
        assert archives == valid_archives
        assert len(pid_files_3) in (workers, 2 * workers)

        os.kill(server.ps.pid, signal.SIGHUP)
        time.sleep(2 * sleep_factor)

        archives, pid_files_4 = files(server.ps.pid)
        assert archives == valid_archives
        assert pid_files_3.isdisjoint(pid_files_4)
        assert name + ' 4000.0' in stats()


def test_gunicorn_worker_exit(wsgi_env, context):
    wsgi_env['start_time'] = time.time()
    wsgi_env['REQUEST_ID'] = 'ID'
    Context.current.request_id = 'ID'
    request = talisker.wsgi.TaliskerWSGIRequest(wsgi_env, None, [])
    talisker.wsgi.REQUESTS['ID'] = request

    gunicorn.gunicorn_worker_exit(None, None)

    context.assert_log(
        name='talisker.wsgi',
        msg='GET /',
        extra={
            'request_id': 'ID',
            'timeout': True,
        },
    )
