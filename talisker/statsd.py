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
