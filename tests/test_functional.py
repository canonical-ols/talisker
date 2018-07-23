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
import os
from time import sleep

import pytest
import requests
from prometheus_client.parser import text_string_to_metric_families

from talisker.testing import GunicornProcess, ServerProcess
from tests.celery_app import basic_task, error_task

APP = 'tests.wsgi_app:application'


def test_gunicorn_sync_worker():
    with GunicornProcess(APP, args=['--worker-class=sync']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


def test_gunicorn_gevent_worker():
    with GunicornProcess(APP, args=['--worker-class=gevent']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


def test_gunicorn_eventlet_worker():
    with GunicornProcess(APP, args=['--worker-class=eventlet']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


def test_flask_app():
    with GunicornProcess('tests.flask_app:app') as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200
    assert response.headers['X-View-Name'] == 'tests.flask_app.index'


def test_django_app(monkeypatch):
    env = os.environ.copy()
    env['PYTHONPATH'] = 'tests/django_app/'
    with GunicornProcess(
            'tests.django_app.django_app.wsgi:application', env=env) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200
    assert response.headers['X-View-Name'] == 'django_app.views.index'


def test_celery_basic():
    cmd = ['talisker.celery', 'worker', '-q', '-A', 'tests.celery_app']

    with ServerProcess(cmd) as pr:
        pr.wait_for_output(' ready.', timeout=30)
        result = basic_task.delay()
        error_result = error_task.delay()

        output = result.wait(timeout=3)
        with pytest.raises(Exception):
            error_result.wait(timeout=3)

    assert output == 'basic'
    assert {
        'logmsg': 'basic task',
        'extra': {'task_name': 'tests.celery_app.basic_task'},
    } in pr.log


def test_multiprocess_metrics(tmpdir):

    def get_count(response):
        for family in text_string_to_metric_families(response.text):
            if family.name == 'test':
                return family.samples[0][-1]

    # ensure we isolate multiprocess metrics
    env = os.environ.copy()
    env.pop('prometheus_multiproc_dir', None)

    with GunicornProcess(APP, args=['-w', '2'], env=env) as p:
        inc = p.url('/_status/test/prometheus')
        read = p.url('/_status/metrics')
        response = requests.get(read)
        initial = get_count(response)
        if initial is None:
            initial = 0

        for i in range(1, 4):
            requests.get(inc)
            # try ensure the update is written before we read it
            sleep(0.3)
            response = requests.get(read)
            assert get_count(response) == float(initial + i)
