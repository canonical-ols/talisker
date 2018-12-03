#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker (see http://github.com/canonical-ols/talisker).
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

import logging
import os
from wsgiref.util import setup_testing_defaults

import pytest

# do this as early as possible, to set up logging in pytest
import talisker.logs
# set up default talisker tests with actual formatting
talisker.logs.configure_test_logging(logging.FileHandler('/dev/null'))
talisker._flush_early_logs()
talisker.logs.supress_noisy_logs()

# make sure prometheus is setup in multiprocess mode. We don't actually use
# this dir in tests, as each test gets it's own directory, but this ensures
# prometheus_client is imported in multiprocess mode
from talisker.prometheus import setup_prometheus_multiproc
setup_prometheus_multiproc(async_mode=False)


import talisker.config
import talisker.context
import talisker.logs
import talisker.util
import talisker.celery
import talisker.sentry
import talisker.testing

# set up test test sentry client
talisker.testing.configure_sentry_client()


@pytest.yield_fixture(autouse=True)
def clean_up(request, tmpdir, monkeypatch):
    """Clean up all globals.

    Sadly, talisker uses some global state.  Namely, stdlib logging module
    globals and thread/greenlet locals. This fixure ensures they are all
    cleaned up each time.
    """

    # make sure don't use talisker's git SHA
    os.environ['TALISKER_REVISION_ID'] = 'unknown'
    multiproc = tmpdir.mkdir('multiproc')
    monkeypatch.setenv('prometheus_multiproc_dir', str(multiproc))

    orig_client = talisker.sentry.get_client()

    yield

    talisker.testing.clear_all()
    # some tests mess with the sentry client
    talisker.sentry.set_client(orig_client)

    # reset stdlib logging
    talisker.logs.reset_logging()
    talisker.logs.configure_test_logging(logging.FileHandler('/dev/null'))

    # clear prometheus file cache
    import prometheus_client.core as core
    # recreate class to clear cache, because cache is a closure...
    core._ValueClass = core._MultiProcessValue()


@pytest.fixture
def config():
    return talisker.config.get_config({})


@pytest.fixture
def environ():
    env = {}
    setup_testing_defaults(env)
    return env


@pytest.fixture
def context():
    ctx = talisker.testing.TestContext()
    ctx.start()
    yield ctx
    ctx.stop()


@pytest.fixture
def django(monkeypatch):
    monkeypatch.setitem(
        os.environ,
        'DJANGO_SETTINGS_MODULE',
        'tests.django_app.django_app.settings')


@pytest.fixture
def no_network(monkeypatch):
    import socket

    def bad_socket(*args, **kwargs):
        assert 0, "socket.socket was used!"

    monkeypatch.setattr(socket, 'socket', bad_socket)
