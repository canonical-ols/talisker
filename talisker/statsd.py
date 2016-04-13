from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import os
from statsd import StatsClient, defaults

from .util import parse_url

_client = None


def get_client():
    global _client

    if _client is None:
        _client = get_client_from_env()

    return _client


def get_client_from_env():
    """Reimplementation of statsd's env config.

    Needed because for some reason statsd does it at import time.
    """
    dsn = os.environ.get('STATSD_DSN', None)
    prefix = defaults.PREFIX
    if dsn is not None:
        parsed = parse_url(dsn, 'udp')
        host = parsed.hostname
        if parsed.port is not None:
            port = int(parsed.port)
        if parsed.username:
            prefix = parsed.username
    else:
        host = os.getenv('STATSD_HOST', defaults.HOST)
        port = int(os.getenv('STATSD_PORT', defaults.PORT))

    if prefix == defaults.PREFIX:
        prefix = os.getenv('STATSD_PREFIX', defaults.PREFIX)

    maxudpsize = int(os.getenv('STATSD_MAXUDPSIZE', defaults.MAXUDPSIZE))
    ipv6 = bool(int(os.getenv('STATSD_IPV6', defaults.IPV6)))

    return StatsClient(host=host, port=port, prefix=prefix,
                       maxudpsize=maxudpsize, ipv6=ipv6)
