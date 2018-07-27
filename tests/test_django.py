#
# Copyright (c) 2015-2018 Canonical, Ltd.
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
        result = client.capture('Message', message='test')
    assert result is not None

    msg = client.remote.get_transport().messages[-1]
    assert msg['tags']['request_id'] == 'id'
    assert msg['extra']['request_id'] == 'id'
    assert msg['extra']['foo'] == 'bar'
