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
from logging import WARN
import sys
import subprocess

import pytest
import requests

import talisker
from talisker import testing


def assert_config(env, **expected):
    cfg = talisker.get_config(env)
    for k, v in expected.items():
        assert cfg[k] == v


def test_get_config(monkeypatch):
    assert_config(
        {},
        devel=False,
        debuglog=None,
        color=False,
        slowquery_threshold=-1,
        logstatus=False,
    )
    assert_config({'DEBUGLOG': '/tmp/log'}, debuglog='/tmp/log')
    assert_config({'TALISKER_COLOR': '1'}, devel=False, color=False)
    assert_config({'TALISKER_LOGSTATUS': '1'}, logstatus=True)

    assert_config(
        {'TALISKER_SLOWQUERY_THRESHOLD': '3000'}, slowquery_threshold=3000)

    assert_config({'DEVEL': '1'}, devel=True, slowquery_threshold=-1)
    assert_config({'DEVEL': '1', 'TERM': 'dumb'}, devel=True, color=False)
    assert_config(
        {'DEVEL': '1', 'TALISKER_SLOWQUERY_THRESHOLD': '3000'},
        devel=True, slowquery_threshold=3000)
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOR': '1'},
        devel=True,
        color='default',
    )
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOR': 'simple'},
        devel=True,
        color='simple',
    )

    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert_config({'DEVEL': '1'}, devel=True, color='default')
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOR': '0'},
        devel=True,
        color=False,
    )


SCRIPT = """
import logging
import test2
logging.getLogger('test').info('test __main__', extra={'foo': 'bar'})
"""


@pytest.fixture
def script(tmpdir):
    subdir = tmpdir.mkdir('pkg')
    py_script = subdir.join('test.py')
    py_script.write(SCRIPT)
    py_script2 = subdir.join('test2.py')
    py_script2.write('')
    return str(py_script)


def test_run_entrypoint(script):
    entrypoint = 'talisker.run'
    output = subprocess.check_output(
        [entrypoint, script],
        stderr=subprocess.STDOUT,
    )
    output = output.decode('utf8')
    assert 'test __main__' in output
    assert 'foo=bar' in output


def test_module_entrypoint(script):
    entrypoint = 'python'
    output = subprocess.check_output(
        [entrypoint, '-m', 'talisker', script],
        stderr=subprocess.STDOUT,
    )
    output = output.decode('utf8')
    assert 'test __main__' in output
    assert 'foo=bar' in output


def test_gunicorn_entrypoint():
    entrypoint = 'talisker'
    subprocess.check_output([entrypoint, '--help'])


def test_celery_entrypoint():
    entrypoint = 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])


@pytest.mark.skipif(sys.version_info[:2] != (3, 6), reason='python 3.6 only')
def test_gunicorn_eventlet_entrypoint():
    # this will error in python3.6 without our fix
    gunicorn = testing.GunicornProcess(
        app='tests.py36_async_tls:app',
        gunicorn='talisker.gunicorn.eventlet',
        args=['--worker-class=eventlet'])
    with gunicorn:
        r = requests.get(gunicorn.url('/'))
    assert r.status_code == 200


@pytest.mark.skipif(sys.version_info[:2] != (3, 6), reason='python 3.6.only')
def test_gunicorn_gevent_entrypoint():
    # this will error in python3.6 without our fix
    gunicorn = testing.GunicornProcess(
        app='tests.py36_async_tls:app',
        gunicorn='talisker.gunicorn.gevent',
        args=['--worker-class=gevent'])
    with gunicorn:
        r = requests.get(gunicorn.url('/'))
    assert r.status_code == 200


@pytest.mark.parametrize('succeed, expected_logs', [
    (True, []),
    (False, [('talisker.initialise', WARN,
              'Unable to create lock for Prometheus, using dummy instead')])])
def test_logging_prometheus_lock(
        succeed, expected_logs, monkeypatch, caplog):
    """EACCES creating the multiprocess.Lock() should log a warning."""
    def fail(*args, **kwargs):
        raise OSError(13, "Permission denied")

    if not succeed:
        monkeypatch.setattr("talisker.Lock", fail)

    talisker.initialise_prometheus_lock()
    assert caplog.record_tuples == expected_logs
