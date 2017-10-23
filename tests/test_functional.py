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
from talisker.testing import GunicornProcess, ServerProcess

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


def test_celery():
    cmd = ['talisker.celery', 'worker', '-q', '-A', 'tests.celery_app']
    from tests.celery_app import job_a, job_b
    with ServerProcess(cmd) as p:
        result = job_a.delay()
        output = result.wait(timeout=2)

    assert output == 'job a'
    assert {
        'logmsg': 'job a',
        'extra': {'task_name': 'tests.celery_app.job_a'},
    } in p.log
