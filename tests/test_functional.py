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
import os

import requests
import pytest
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


def test_django_app(monkeypatch):
    env = os.environ.copy()
    env['PYTHONPATH'] = 'tests/django_app/'
    with GunicornProcess(
            'tests.django_app.django_app.wsgi:application', env=env) as p:
        response = requests.get(p.url('/'))
        assert response.status_code == 200


def test_celery_basic():
    cmd = ['talisker.celery', 'worker', '-q', '-A', 'tests.celery_app']

    with ServerProcess(cmd) as pr:
        result = basic_task.delay()
        output = result.wait(timeout=2)

        #error_result = error_task.delay()
        #with pytest.raises(Exception):
        #    error_result.wait(timeout=3)

    assert output == 'basic'
    assert {
        'logmsg': 'basic task',
        'extra': {'task_name': 'tests.celery_app.basic_task'},
    } in pr.log
