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

import os
from urllib.parse import urlparse, parse_qs
from statsd import StatsClient, defaults

__all__ = ['get_client']

_client = None


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


def get_client(dsn=None):
    global _client

    if _client is None:
        if dsn is None:
            dsn = os.environ.get('STATSD_DSN', None)
        if dsn is None:
            _client = DummyClient()
        else:
            if not dsn.startswith('udp'):
                raise Exception('Talisker only supports udp stastd client')
            _client = StatsClient(*parse_statsd_dsn(dsn))

    return _client


class DummyClient(StatsClient):
    def _after(self, stat):
        pass
