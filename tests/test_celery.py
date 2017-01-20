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

import talisker.celery

DATESTRING = '2016-01-02 03:04:05.1234'
TIMESTAMP = 1451703845.1234


@pytest.fixture
def celery_app():
    talisker.celery.enable_signals()
    app = celery.Celery()
    app.conf.update(CELERY_ALWAYS_EAGER=True)

    try:
        yield app
    finally:
        talisker.celery.disable_signals()


def test_celery_entrypoint():
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])


@freeze_time(DATESTRING)
def test_task_publish_hook(statsd_metrics):
    headers = {}

    with talisker.request_id.context('test'):
        talisker.celery.before_task_publish('task', {'id': 'xxx'}, headers)

    assert 'talisker_enqueue_start' in headers
    assert headers['talisker_request_id'] == 'test'
    headers['talisker_enqueue_start'] -= 1

    talisker.celery.after_task_publish('task', {'id': 'xxx'}, headers)
    assert statsd_metrics[0] == 'celery.task.enqueue:1000.000000|ms'
    assert 'talisker_enqueue_start' not in headers


# stub Task object
def task():
    class Task():
        pass
    t = Task()
    t.name = 'task'
    t.id = 'xxx'
    t.request = Task()
    t.request.id = t.id
    return t


@freeze_time(DATESTRING)
def test_task_run_hook(statsd_metrics):
    t = task()

    t.request.talisker_request_id = 'test'
    talisker.celery.task_prerun(t, t.id, t)

    assert t.talisker_timer._start_time == TIMESTAMP
    assert talisker.request_id.get() == 'test'
    assert talisker.logs.logging_context['task_id'] == t.id
    assert talisker.logs.logging_context['task_name'] == t.name

    t.talisker_timer._start_time -= 1

    talisker.celery.task_postrun(t, t.id, t)
    assert statsd_metrics[0] == 'celery.task.run:1000.000000|ms'
    assert talisker.request_id.get() is None
    assert 'task_id' not in talisker.logs.logging_context
    assert 'task_name' not in talisker.logs.logging_context


@freeze_time(DATESTRING)
def test_task_counter(statsd_metrics):
    signal = talisker.celery._counter('name')
    t = task()
    signal(t)
    assert statsd_metrics[0] == 'celery.task.name:1|c'


def apply(task):
    # celery's apply doesn't send the publishing signals, so we fake it, as
    # ours only need the headers dict
    headers = {}
    talisker.celery.before_task_publish(None, None, headers)
    task.apply(headers=headers)
    talisker.celery.after_task_publish(None, None, headers)


def test_celery_task_logging(celery_app, log):

    @celery_app.task
    def task():
        logging.getLogger(__name__).info('stdlib')
        # test celery's special task logger
        get_task_logger(__name__).info('task')

    request_id = 'myid'

    with talisker.request_id.context(request_id):
        apply(task)

    record = [l for l in log if l.msg == 'stdlib'][0]
    assert record._structured['task_name'] == task.name
    assert record._structured['request_id'] == request_id
    assert 'task_id' in record._structured

    record = [l for l in log if l.msg == 'task'][0]
    assert record._structured['task_name'] == task.name
    assert record._structured['request_id'] == request_id
    assert 'task_id' in record._structured


def test_celery_task_sentry(celery_app, sentry_messages):

    @celery_app.task
    def error():
        raise Exception('test')

    request_id = 'myid'

    with talisker.request_id.context(request_id):
        apply(error)

    assert len(sentry_messages) == 1
    msg = sentry_messages[0]
    assert msg['extra']['task_name'] == error.name
    assert 'task_id' in msg['extra']
    assert msg['tags']['request_id'] == request_id
