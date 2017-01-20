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
import pytest

import talisker.django
import talisker.sentry
from tests import conftest


@pytest.fixture
def django(monkeypatch):
    monkeypatch.setitem(
        os.environ,
        'DJANGO_SETTINGS_MODULE',
        'tests.django_app.django_app.settings')


def test_django_client_init(log, monkeypatch):
    called = [False]

    def hook():
        called[0] = True

    monkeypatch.setattr('raven.contrib.django.client.install_sql_hook', hook)
    client = talisker.django.SentryClient(
        dsn=conftest.DSN,
        install_sql_hook=True,
    )

    assert called[0] is False
    assert set(client.processors) == talisker.sentry.default_processors
    assert 'configured raven' in log[-1].msg
    assert talisker.sentry.get_client() is client
    assert talisker.sentry.get_log_handler().client is client


def test_django_client_capture(django):
    client = talisker.django.SentryClient(
        dsn=conftest.DSN,
        transport=conftest.DummyTransport,
    )
    with talisker.logs.logging_context(request_id='id', foo='bar'):
        client.capture('Message', message='test')

    msg = client.remote.get_transport().messages[-1]
    assert msg['tags']['request_id'] == 'id'
    assert msg['extra']['request_id'] == "'id'"
    assert msg['extra']['foo'] == "'bar'"
