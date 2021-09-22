#
# Copyright (c) 2015-2021 Canonical, Ltd.
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

import inspect
import os
import textwrap
from time import sleep
import sys

import pytest
import requests


from tests.conftest import require_module
from talisker.testing import GunicornProcess, ServerProcess, request_id
from talisker.context import Context

APP = 'tests.wsgi_app:application'


@require_module('gunicorn')
def test_gunicorn_sync_worker():
    with GunicornProcess(APP, args=['--worker-class=sync']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


@require_module('gunicorn')
@require_module('gevent')
def test_gunicorn_gevent_worker():
    with GunicornProcess(APP, args=['--worker-class=gevent']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


@require_module('gunicorn')
@require_module('eventlet')
@pytest.mark.skipif(
    sys.version_info >= (3, 7),
    reason='eventlet not supported on py37. Can be re-enabled after this is '
           'merged: https://github.com/benoitc/gunicorn/pull/2581 and '
           'updating eventlet to 0.31.0',
)
def test_gunicorn_eventlet_worker():
    with GunicornProcess(APP, args=['--worker-class=eventlet']) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200


@require_module('gunicorn')
def test_gunicorn_status_interface():
    args = ['--bind', '127.0.0.2:0']  # additional bind
    env = os.environ.copy()
    env['TALISKER_REVISION_ID'] = 'test-rev-id'
    env['TALISKER_STATUS_INTERFACE'] = '127.0.0.2'
    with GunicornProcess('tests.wsgi_app:app404', args=args, env=env) as p:
        resp1 = requests.get(p.url('/_status/check', iface='127.0.0.1'))
        resp2 = requests.get(p.url('/_status/check', iface='127.0.0.2'))
    assert resp1.status_code == 404
    assert resp1.text == 'Not Found'
    assert resp2.status_code == 200
    assert resp2.text == 'test-rev-id\n'


@require_module('flask')
@require_module('gunicorn')
def test_flask_app():
    try:
        import flask  # noqa
    except ImportError:
        pytest.skip('need flask installed')

    with GunicornProcess('tests.flask_app:app') as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200
    assert response.headers['X-View-Name'] == 'tests.flask_app.index'


@require_module('gunicorn')
@require_module('django')
def test_django_app(django):
    try:
        import django  # noqa
    except ImportError:
        pytest.skip('need django installed')

    app = 'tests.django_app.django_app.wsgi:application'

    with GunicornProcess(app) as p:
        response = requests.get(p.url('/'))
    assert response.status_code == 200
    assert response.headers['X-View-Name'] == 'django_app.views.index'


@require_module('gunicorn')
def test_gunicorn_timeout(tmpdir):

    def test_app():
        import time

        def app(environ, start_response):
            start_response('200 OK', [('content-type', 'text/plain')])
            time.sleep(100)
            return []

    app_module = str(tmpdir / 'app.py')
    with open(app_module, 'w') as f:
        f.write(get_function_body(test_app))

    # ensure devel mode
    env = os.environ.copy()
    env['DEVEL'] = '1'
    p = GunicornProcess('app:app', args=['-t1'], cwd=str(tmpdir), env=env)
    with p:
        response = requests.get(
            p.url('/'),
            headers={'Accept': 'application/json'},
        ).json()

    assert response['title'].startswith(
        'RequestTimeout: gunicorn worker timeout (pid:'
    )


@require_module('celery')
def test_celery_basic(celery_signals):
    from tests.celery_app import basic_task, error_task, propagate_task
    cmd = ['talisker.celery', '-q', '-A', 'tests.celery_app', 'worker']

    with ServerProcess(cmd) as pr:
        pr.wait_for_output(' ready.', timeout=30)
        Context.new()
        result = basic_task.delay()
        error_result = error_task.delay()

        with request_id('myid'):
            propagate = propagate_task.delay()

        output = result.wait(timeout=3)
        with pytest.raises(Exception):
            error_result.wait(timeout=3)
        propagate.wait(timeout=3)

    assert output == 'basic'
    pr.log.assert_log(
        msg='basic task',
        extra={'task_name': 'tests.celery_app.basic_task'},
    )
    pr.log.assert_log(
        msg='propagate_task',
        extra={'request_id': 'myid'},
    )


@require_module('prometheus_client')
def test_multiprocess_metrics(tmpdir):
    from prometheus_client.parser import text_string_to_metric_families

    def get_count(response):
        for family in text_string_to_metric_families(response.text):
            if family.name == 'test':
                return family.samples[0][2]

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

        for i in range(1, 3):
            requests.get(inc)
            # try ensure the update is written before we read it
            sleep(1)
            response = requests.get(read)
            assert get_count(response) == float(initial + i)


def get_function_body(func):
    """Extract the body of a function.

    This can be used instead of an embedded string to define python code that
    needs to be used as a string. It means that the code in question can be
    edited, parsed, autocompleted and linting as normal python code.
    """
    lines = inspect.getsourcelines(func)
    return textwrap.dedent('\n'.join(lines[0][1:]))


@require_module('prometheus_client')
def test_prometheus_lock_timeouts(tmpdir):

    def test_app():
        from talisker import prometheus
        prometheus.setup_prometheus_multiproc(async_mode=False)
        prometheus._lock.acquire()

        def app(environ, start_response):
            try:
                with prometheus.try_prometheus_lock(0.5):
                    result = b'no timeout'
            except prometheus.PrometheusLockTimeout:
                result = b'timeout'

            start_response('200 OK', [('content-type', 'text/plain')])
            return [result]

    app_module = str(tmpdir / 'app.py')
    with open(app_module, 'w') as f:
        f.write(get_function_body(test_app))

    with GunicornProcess('app:app', args=['-w', '2'], cwd=str(tmpdir)) as p:
        response = requests.get(p.url('/'))
        assert response.text == 'timeout'
