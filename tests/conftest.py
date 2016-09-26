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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from collections import OrderedDict
import logging
import os

from wsgiref.util import setup_testing_defaults

import pytest

from talisker.request_context import request_context
from talisker import logs
import talisker.statsd
import talisker.celery
logs.configure_test_logging()


@pytest.yield_fixture(autouse=True)
def clean_up_context():
    """Clean up all globals.

    Sadly, talisker uses some global state.  Namely, stdlib logging module
    globals and thread/greenlet locals. This fixure ensures they are all
    cleaned up each time.
    """
    yield

    # thread locals
    request_context.__release_local__()
    talisker.celery._local.__release_local__()
    # module globals
    talisker.statsd._client = None
    # reset logging
    logs.StructuredLogger._extra = OrderedDict()
    logs.StructuredLogger._prefix = ''
    logs._logging_configured = False
    logging.getLogger().handlers = []


@pytest.fixture
def environ():
    env = {}
    setup_testing_defaults(env)
    return env


@pytest.fixture
def log():
    handler = logging.handlers.BufferingHandler(10000)
    try:
        logs.add_talisker_handler(logging.NOTSET, handler)
        yield handler.buffer
    finally:
        handler.flush()
        logging.getLogger().handlers.remove(handler)


@pytest.fixture
def metrics(monkeypatch):
    monkeypatch.delitem(os.environ, 'STATSD_DSN', raising=False)
    client = talisker.statsd.get_client()
    pipeline = client.pipeline()
    monkeypatch.setattr(talisker.statsd, '_client', pipeline)
    return pipeline._stats


def run_wsgi(app, environ):
    output = {}

    def start_response(status, headers, exc_info=None):
        output['status'] = status
        output['headers'] = headers

    body = app(environ, start_response)

    return body, output['status'], output['headers']
