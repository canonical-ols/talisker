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
__metaclass__ = type

from contextlib import contextmanager
from future.moves.urllib.parse import urlparse, parse_qs

from statsd import defaults
from statsd.client import StatsClient

import talisker
from talisker.util import module_cache

__all__ = ['get_client']


def parse_statsd_dsn(dsn):
    parsed = urlparse(dsn)
    host = parsed.hostname
    port = parsed.port or defaults.PORT
    prefix = None
    if parsed.path:
        prefix = parsed.path.strip('/').replace('/', '.')
    ipv6 = parsed.scheme in ('udp6', 'tcp6')
    size = int(
        parse_qs(parsed.query).get('maxudpsize', [defaults.MAXUDPSIZE])[0])
    return host, port, prefix, size, ipv6


@module_cache
def get_client():
    client = None
    dsn = talisker.get_config().statsd_dsn
    if dsn is None:
        client = DummyClient()
    else:
        if not dsn.startswith('udp'):
            raise Exception('Talisker only supports udp stastd client')
        client = StatsClient(*parse_statsd_dsn(dsn))

    return client


class DummyClient(StatsClient):  # lgtm [py/missing-call-to-init]
    """Mock client for statsd that can collect data when testing."""
    _prefix = ''  # force no prefix

    def __init__(self, collect=False):
        # Note: do *not* call super(), as that will create udp socket we don't
        # want.
        if collect:
            self.stats = MetricList()
        else:
            self.stats = None

    def _send(self, data):  # lgtm [py/inheritance/signature-mismatch]
        if self.stats is not None:
            self.stats.append(data)

    def pipeline(self):
        return self.__class__(collect=True)

    # pipeline methods
    def send(self):
        if self.stats:
            self.stats[:] = []

    def __enter__(self):
        return self

    def __exit__(self, typ, value, tb):
        self.send()

    # test helper methods
    @contextmanager
    def collect(self):
        orig_stats = self.stats
        self.stats = []
        yield self.stats
        self.stats = orig_stats


class MetricList(list):
    """A container for searching a list of statsd metrics."""

    def filter(self, name):
        filtered = self.__class__()
        for metric in self:
            if name in metric:
                filtered.append(metric)
        return filtered
