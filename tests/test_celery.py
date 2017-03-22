# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import logging
import subprocess
import os

import celery
from celery.utils.log import get_task_logger

import pytest
from freezegun import freeze_time
from celery.result import allow_join_result
from celery import signals
import talisker.celery
import talisker.logs

# celerytest imports are broken internally broken in py3
import sys
import pkg_resources
path = os.path.join(
    pkg_resources.get_distribution('celerytest').location, 'celerytest')
sys.path.append(path)
from celerytest.worker import CeleryWorkerThread
sys.path.pop()


DATESTRING = '2016-01-02 03:04:05.1234'
TIMESTAMP = 1451703845.1234
app = celery.Celery()
talisker.celery.enable_signals()
logging.getLogger('kombu').propagate = False
app.conf.update(
    BROKER_URL='memory://localhost/',
    CELERYD_CONCURRENCY=1,
    CELERYD_POOL='solo',
    CELERY_SEND_EVENTS=True,
    CELERY_RESULT_BACKEND='db+sqlite:///results??mode=memory&cache=shared',
)


# magically make every enqueue take 1 second.
@celery.signals.before_task_publish.connect
def before_task_publish(sender, body, headers, **kwargs):
    store = talisker.celery.get_store(body, headers)
    t = store.get(talisker.celery.ENQUEUE_START)
    if t:
        store[talisker.celery.ENQUEUE_START] = t - 1.0


# magically make every task take 2 seconds
@celery.signals.task_prerun.connect
def task_prerun(sender, task_id, task, **kwargs):
    task.talisker_timer._start_time -= 2.0


class TaliskerCeleryWorkerThread(CeleryWorkerThread):
    def run(self):
        talisker.celery.enable_signals()
        signals.worker_init.connect(self.on_worker_init)
        signals.worker_ready.connect(self.on_worker_ready)

        self.monitor.daemon = self.daemon
        self.monitor.start()

        worker = self.app.Worker()
        # not .run()
        worker.start()


# tasks need definining at import time to be registered correctly with the
# results_backend
@app.task(bind=True)
def dummy_task(self):
    logging.getLogger(__name__).info('stdlib')
    # test celery's special task logger
    get_task_logger(__name__).info('task')
    return self.request


@app.task()
def error_task():
    raise Exception('error')


@pytest.fixture
def celery_app():
    worker = TaliskerCeleryWorkerThread(app)
    worker.daemon = True
    worker.start()
    worker.ready.wait()
    with allow_join_result():
        yield app
    worker.idle.wait()


@freeze_time(DATESTRING)
def test_celery_task(celery_app, statsd_metrics, log):
    request_id = 'myid'

    with talisker.request_id.context(request_id):
        request = dummy_task.delay().get()

    assert talisker.celery.get_header(request, talisker.celery.ENQUEUE_START)
    assert talisker.celery.get_header(
        request, talisker.celery.REQUEST_ID) == 'myid'

    assert 'dummy_task.enqueue:1000.000000|ms' in statsd_metrics[0]
    assert 'dummy_task.success:1|c' in statsd_metrics[1]
    assert 'dummy_task.run:2000.000000|ms' in statsd_metrics[2]

    logs = [l for l in log if l.name == __name__]
    assert logs[0].msg == 'stdlib'
    assert logs[0]._structured['task_id'] == request.id
    assert logs[0]._structured['task_name'] == dummy_task.name
    assert logs[0]._structured['request_id'] == request_id

    assert logs[1].msg == 'task'
    assert logs[1]._structured['task_id'] == request.id
    assert logs[1]._structured['task_name'] == dummy_task.name
    assert logs[1]._structured['request_id'] == request_id


def test_celery_task_sentry(celery_app, statsd_metrics, sentry_messages):
    request_id = 'myid'

    with talisker.request_id.context(request_id):
        request = error_task.delay()

    with pytest.raises(Exception):
        request.get()

    assert 'error_task.failure:1|c' in statsd_metrics[1]
    assert len(sentry_messages) == 1
    msg = sentry_messages[0]
    assert msg['extra']['task_name'] == error_task.name
    assert 'task_id' in msg['extra']
    assert msg['tags']['request_id'] == request_id


def test_celery_entrypoint():
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])
