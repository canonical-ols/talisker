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

# make sure prometheus is setup in multiprocess mode. We don't actually use
# this dir in tests, as each test gets it's own directory, but this ensures
# prometheus_client is imported in multiprocess mode
from talisker import setup_multiproc_dir
setup_multiproc_dir()

# do this as early as possible, to set up logging in pytest
import talisker.logs
talisker.logs.configure_test_logging()
talisker.logs.supress_noisy_logs()

import ast
import logging
import json
from wsgiref.util import setup_testing_defaults
import zlib

import pytest

import raven.breadcrumbs
import raven.transport
import raven.base
import raven.context

import talisker.context
import talisker.logs
import talisker.util
import talisker.celery
import talisker.revision
import talisker.endpoints
import talisker.sentry
import talisker.testing


@pytest.yield_fixture(autouse=True)
def clean_up(tmpdir, monkeypatch):
    """Clean up all globals.

    Sadly, talisker uses some global state.  Namely, stdlib logging module
    globals and thread/greenlet locals. This fixure ensures they are all
    cleaned up each time.
    """

    multiproc = tmpdir.mkdir('multiproc')
    monkeypatch.setenv('prometheus_multiproc_dir', str(multiproc))

    yield

    talisker.testing.clear_all()

    # reset stdlib logging
    talisker.logs.reset_logging()
    talisker.logs.configure_test_logging()

    # clear prometheus file cache
    import prometheus_client.core as core
    # recreate class to clear cache, because cache is a closure...
    core._ValueClass = core._MultiProcessValue()


@pytest.fixture
def config():
    return {
        'devel': False,
        'debuglog': None,
        'color': False,
    }


@pytest.fixture
def environ():
    env = {}
    setup_testing_defaults(env)
    return env


@pytest.fixture
def log():
    handler = logging.handlers.BufferingHandler(10000)
    try:
        talisker.logs.add_talisker_handler(logging.NOTSET, handler)
        yield handler.buffer
    finally:
        handler.flush()
        logging.getLogger().handlers.remove(handler)


@pytest.fixture
def no_network(monkeypatch):
    import socket

    def bad_socket(*args, **kwargs):
        assert 0, "socket.socket was used!"

    monkeypatch.setattr(socket, 'socket', bad_socket)


@pytest.fixture
def statsd_metrics(monkeypatch):
    client = talisker.statsd.DummyClient()
    talisker.statsd.get_client.raw_update(client)
    with client.collect() as stats:
        yield stats


class DummyTransport(raven.transport.Transport):
    scheme = ['test']

    def __init__(self, *args, **kwargs):
        # raven 5.x passes url, raven 6.x doesn't. We don't care, so *args it
        self.kwargs = kwargs
        self.messages = []

    def send(self, *args, **kwargs):
        # In raven<6, args = (data, headers).
        # In raven 6.x args = (url, data, headers)
        if len(args) == 2:
            data, _ = args
        elif len(args) == 3:
            _, data, _ = args
        else:
            raise Exception('raven Transport.send api seems to have changed')
        raw = json.loads(zlib.decompress(data).decode('utf8'))
        # to make asserting easier, parse json strings into python strings
        for k, v in list(raw['extra'].items()):
            try:
                val = ast.literal_eval(v)
                raw['extra'][k] = val
            except Exception:
                pass

        self.messages.append(raw)


DSN = 'http://user:pass@host/project'


@pytest.fixture
def sentry_client(dsn=DSN):
    client = talisker.sentry.configure_client(
        dsn=dsn, transport=DummyTransport)
    return client


@pytest.fixture
def sentry_messages(sentry_client):
    transport = sentry_client.remote.get_transport()
    return transport.messages


def run_wsgi(app, environ):
    output = {}

    def start_response(status, headers, exc_info=None):
        output['status'] = status
        output['headers'] = headers

    body = app(environ, start_response)

    return body, output['status'], output['headers']
