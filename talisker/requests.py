from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import requests
from . import statsd
from .util import parse_url
from .request_id import get_request_id

_session = None



def get_session():
    global _session
    if _session is None:
        _session = new_session()
    return _session


def new_session(cls=requests.Session):
    session = cls()
    # insert metrics hook first as it needs response, and does't
    # alter hook_data for later hooks
    session.hooks['response'].insert(0, metrics_response_hook)
    return session


def metrics_response_hook(response, **kwargs):
    """Response hook that records statsd metrics"""
    name, duration = get_timing(response)
    statsd.get_client().timing(prefix, duration)


def get_timing(response):
    parsed = parse_url(response.request.url)
    duration = response.elapsed.total_seconds() * 1000
    prefix = 'requests.{}.{}.{}.{}'.format(
        parsed.hostname.replace('.', '-'),
        parsed.path.replace('/', '_'),
        response.request.method.upper(),
        str(response.status_code),
    )
    return prefix, duration
