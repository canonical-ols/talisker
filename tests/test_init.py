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
import sys
import subprocess

import pytest
import requests

from talisker import testing


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
