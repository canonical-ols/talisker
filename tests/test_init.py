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
