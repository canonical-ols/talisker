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

import ast
import logging
import os
import zlib
import json
from wsgiref.util import setup_testing_defaults

import pytest

import raven.breadcrumbs
import raven.transport
import raven.base

import talisker.context
import talisker.logs
import talisker.util
import talisker.celery
import talisker.revision
import talisker.endpoints
import talisker.sentry

# set basic logging
talisker.logs.set_logger_class()
talisker.logs.configure_warnings(True)


@pytest.yield_fixture(autouse=True)
def clean_up():
    """Clean up all globals.

    Sadly, talisker uses some global state.  Namely, stdlib logging module
    globals and thread/greenlet locals. This fixure ensures they are all
    cleaned up each time.
    """
    yield

    # module/context globals
    talisker.util.clear_globals()
    # reset stdlib logging
    talisker.logs.reset_logging()
    # reset context storage
    talisker.context.clear()


@pytest.fixture
def config():
    return {
        'devel': False,
        'debuglog': None,
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
    # avoid users environment causing failures
    monkeypatch.delitem(os.environ, 'STATSD_DSN', raising=False)
    client = talisker.statsd.get_client()
    with client.collect() as stats:
        yield stats


@pytest.fixture
def prometheus_metrics(monkeypatch):
    # avoid users environment causing failures
    monkeypatch.delitem(os.environ, 'prometheus_multiproc_dir', raising=False)


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
            except:
                pass

        self.messages.append(raw)


DSN = 'http://user:pass@host/project'


@pytest.fixture
def sentry_client(dsn=DSN):
    return talisker.sentry.configure_client(
        dsn=dsn, transport=DummyTransport)


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
