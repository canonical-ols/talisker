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

import pytest

try:
    import django  # noqa
except ImportError:
    pytest.skip("skipping django only tests", allow_module_level=True)

import talisker.django
import talisker.sentry
from talisker.testing import TEST_SENTRY_DSN


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_django_sentry_client(monkeypatch, context):
    from talisker.sentry import DummySentryTransport
    called = [False]

    def hook():
        called[0] = True

    monkeypatch.setattr('raven.contrib.django.client.install_sql_hook', hook)
    client = talisker.django.SentryClient(
        dsn=TEST_SENTRY_DSN,
        transport=DummySentryTransport,
        install_sql_hook=True,
    )

    assert called[0] is False
    assert set(client.processors) == talisker.sentry.default_processors
    context.assert_log(msg='configured raven')
    assert talisker.sentry.get_client() is client
    assert talisker.sentry.get_log_handler().client is client
