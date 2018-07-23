#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
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
