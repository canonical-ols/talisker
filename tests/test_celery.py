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

import pytest
from freezegun import freeze_time

import talisker.celery
from talisker import request_id

DATESTRING = '2016-01-02 03:04:05.1234'
TIMESTAMP = 1451703845.1234


@pytest.fixture
def celery_app():
    app = celery.Celery()
    app.conf.update(CELERY_ALWAYS_EAGER=True)
    return app


def test_log(log, celery_app):

    logger = logging.getLogger(__name__)

    @celery_app.task
    @talisker.celery.log
    def foo(a):
        logger.info('test')

    with request_id.context('id'):
        talisker.celery.delay(foo, 1).get()
    tags = log[0]._structured
    assert tags['request_id'] == 'id'
    assert len(tags['task_id']) == 36  # uuid


def test_celery_entrypoint():
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])


@freeze_time(DATESTRING)
def test_task_publish_metrics(statsd_metrics):
    talisker.celery.before_task_publish('task', {'id': 'xxx'})
    timer = talisker.celery._local.timers['xxx']
    assert timer._start_time == TIMESTAMP

    timer._start_time -= 1

    talisker.celery.after_task_publish('task', {'id': 'xxx'})
    assert statsd_metrics[0] == 'celery.task.enqueue:1000.000000|ms'
    assert 'xxx' not in talisker.celery._local.timers


# stub Task object
def task():
    class Task():
        pass
    t = Task()
    t.name = 'task'
    t.id = 'xxx'
    return t


@freeze_time(DATESTRING)
def test_task_run_metrics(statsd_metrics):
    t = task()
    talisker.celery.task_prerun(t, t.id, t)
    assert t.__talisker_timer._start_time == TIMESTAMP

    t.__talisker_timer._start_time -= 1

    talisker.celery.task_postrun(t, t.id, t)
    assert statsd_metrics[0] == 'celery.task.run:1000.000000|ms'


@freeze_time(DATESTRING)
def test_task_counter(statsd_metrics):
    signal = talisker.celery._counter('name')
    t = task()
    signal(t)
    assert statsd_metrics[0] == 'celery.task.name:1|c'
