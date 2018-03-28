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

import celery
from celery.utils.log import get_task_logger

from freezegun import freeze_time
import pytest
import talisker.celery
import talisker.logs


DATESTRING = '2016-01-02 03:04:05.1234'
TIMESTAMP = 1451703845.1234


# make enqueue always take 1s
def before_task_publish(sender, body, headers, **kwargs):
    store = talisker.celery.get_store(body, headers)
    t = store.get(talisker.celery.ENQUEUE_START)
    if t:
        store[talisker.celery.ENQUEUE_START] = t - 1.0


# make task run always take 2s
def task_prerun(sender, task_id, task, **kwargs):
    task.talisker_timestamp -= 2.0


@pytest.fixture
def celery_app():
    # reregister all the signals and sentry clients
    talisker.celery.enable_signals()
    celery.signals.before_task_publish.connect(before_task_publish)
    celery.signals.task_prerun.connect(task_prerun)

    yield celery.Celery(broker='memory://localhost/')

    celery.signals.before_task_publish.disconnect(before_task_publish)
    celery.signals.task_prerun.disconnect(task_prerun)
    talisker.celery.disable_signals()


@freeze_time(DATESTRING)
def test_celery_task_enqueue(celery_app, statsd_metrics, log):
    request_id = 'myid'

    with talisker.request_id.context(request_id):
        celery_app.send_task('test_task')

    assert statsd_metrics == [
        'celery.count.test_task:1|c',
        'celery.latency.enqueue.test_task:1000.000000|ms',
    ]


@freeze_time(DATESTRING)
def test_celery_task_run(celery_app, statsd_metrics, log):
    request_id = 'myid'
    task_id = 'task_id'

    @celery_app.task
    def dummy_task():
        logging.getLogger(__name__).info('stdlib')
        # test celery's special task logger
        get_task_logger(__name__).info('task')

    dummy_task.apply(
        task_id=task_id,
        headers={
            talisker.celery.REQUEST_ID: request_id,
            talisker.celery.ENQUEUE_START: TIMESTAMP - 1.0
        })

    assert statsd_metrics == [
        'celery.latency.queue.tests.test_celery.dummy_task:1000.000000|ms',
        'celery.success.tests.test_celery.dummy_task:1|c',
        'celery.latency.run.tests.test_celery.dummy_task:2000.000000|ms',
    ]

    logs = [l for l in log if l.name == __name__]
    assert logs[0].msg == 'stdlib'
    assert logs[0]._structured['task_id'] == task_id
    assert logs[0]._structured['task_name'] == dummy_task.name
    assert logs[0]._structured['request_id'] == request_id

    assert logs[1].msg == 'task'
    assert logs[1]._structured['task_id'] == task_id
    assert logs[1]._structured['task_name'] == dummy_task.name
    assert logs[1]._structured['request_id'] == request_id


@freeze_time(DATESTRING)
def test_celery_task_run_retry(celery_app, statsd_metrics, log):

    @celery_app.task(bind=True)
    def job_retry(self):
        try:
            raise Exception('failed task')
        except Exception:
            self.retry(countdown=1, max_retries=2)

    job_retry.apply()

    assert statsd_metrics == [
        'celery.latency.run.tests.test_celery.job_retry:2000.000000|ms',
        'celery.retry.tests.test_celery.job_retry:1|c',
        'celery.latency.run.tests.test_celery.job_retry:2000.000000|ms',
        'celery.retry.tests.test_celery.job_retry:1|c',
        'celery.failure.tests.test_celery.job_retry:1|c',
        'celery.latency.run.tests.test_celery.job_retry:2000.000000|ms',
    ]


@freeze_time(DATESTRING)
def test_celery_sentry(celery_app, statsd_metrics, sentry_messages):
    request_id = 'myid'
    task_id = 'task_id'

    @celery_app.task
    def error_task():
        raise Exception('error')

    with talisker.request_id.context(request_id):
        error_task.apply(task_id=task_id)

    assert statsd_metrics == [
        'celery.failure.tests.test_celery.error_task:1|c',
        'celery.latency.run.tests.test_celery.error_task:2000.000000|ms',
    ]

    assert len(sentry_messages) == 1
    msg = sentry_messages[0]
    assert msg['extra']['task_name'] == error_task.name
    assert 'task_id' in msg['extra']
    assert msg['tags']['request_id'] == request_id


def test_celery_entrypoint():
    entrypoint = 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])
