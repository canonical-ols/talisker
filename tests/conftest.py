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

import logging
import os
from wsgiref.util import setup_testing_defaults

import pytest

# do this as early as possible, to set up logging in pytest
import talisker.logs
import talisker.util

# set up default talisker tests with actual formatting
talisker.logs.configure_test_logging(logging.FileHandler('/dev/null'))
talisker.util.flush_early_logs()
talisker.logs.supress_noisy_logs()

# make sure prometheus is setup in multiprocess mode. We don't actually use
# this dir in tests, as each test gets it's own directory, but this ensures
# prometheus_client is imported in multiprocess mode
from talisker.prometheus import setup_prometheus_multiproc
setup_prometheus_multiproc(async_mode=False)

import talisker.context
import talisker.config
import talisker.logs
import talisker.util
import talisker.celery
import talisker.sentry
import talisker.testing

# set up test test sentry client
talisker.sentry.configure_testing(talisker.testing.TEST_SENTRY_DSN)

# create the sentry client up front
if talisker.sentry.enabled:
    talisker.sentry.get_client()

# clear up any initial contexts created from startup code
talisker.context.Context.clear()


@pytest.yield_fixture(autouse=True)
def clean_up(request, tmpdir, monkeypatch, config):
    """Clean up all globals.

    Sadly, talisker uses some global state.  Namely, stdlib logging module
    globals and thread/greenlet locals. This fixure ensures they are all
    cleaned up each time.
    """

    multiproc = tmpdir.mkdir('multiproc')
    monkeypatch.setenv('prometheus_multiproc_dir', str(multiproc))
    orig_client = talisker.sentry._client

    yield

    talisker.testing.clear_all()
    # some tests mess with the sentry client
    talisker.sentry.set_client(orig_client)

    # reset stdlib logging
    talisker.logs.reset_logging()
    talisker.logs.configure_test_logging(logging.FileHandler('/dev/null'))

    # reset metrics
    talisker.testing.reset_prometheus()


@pytest.fixture
def environ():
    return {
        # or else we get talisker's git hash when running tests
        'TALISKER_REVISION_ID': 'test-rev-id',
    }


@pytest.fixture
def config(environ):
    config = talisker.config.Config(environ)
    talisker.get_config.raw_update(config)
    return config


@pytest.fixture
def wsgi_env():
    talisker.Context.new()
    env = {'REMOTE_ADDR': '127.0.0.1'}
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
    root = os.path.dirname(__file__)
    monkeypatch.setitem(
        os.environ,
        'PYTHONPATH',
        os.path.join(root, 'django_app')
    )


@pytest.fixture
def no_network(monkeypatch):
    import socket

    def bad_socket(*args, **kwargs):
        assert 0, "socket.socket was used!"

    monkeypatch.setattr(socket, 'socket', bad_socket)


try:
    import raven.context
except ImportError:
    @pytest.fixture
    def get_breadcrumbs():
        return lambda: None
else:
    @pytest.fixture
    def get_breadcrumbs():
        with raven.context.Context() as ctx:
            yield ctx.breadcrumbs.get_buffer


@pytest.fixture
def celery_signals():
    talisker.celery.enable_signals()
    yield
    talisker.celery.disable_signals()


def require_module(module):
    try:
        __import__(module)
    except ImportError:
        return pytest.mark.skip(reason='{} is not installed'.format(module))
    else:
        return lambda f: f
