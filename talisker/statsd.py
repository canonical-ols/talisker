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
import logging
from contextlib import contextmanager

from future.moves.urllib.parse import urlparse, parse_qs

from talisker.util import module_cache
from statsd import defaults
from statsd.client import StatsClientBase, StatsClient

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
    logger = logging.getLogger(__name__)
    dsn = os.environ.get('STATSD_DSN', None)
    if dsn is None:
        client = DummyClient()
        logger.info('configuring statsd DummyClient')
    else:
        if not dsn.startswith('udp'):
            raise Exception('Talisker only supports udp stastd client')
        client = StatsClient(*parse_statsd_dsn(dsn))
        logger.info(
            'configuring statsd via environment',
            extra={'STATSD_DSN': dsn})

    return client


class DummyClient(StatsClientBase):
    _prefix = ''

    def __init__(self, collect=False):
        if collect:
            self.stats = []
        else:
            self.stats = None

    def _send(self, data):
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
