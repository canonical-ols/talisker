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

import logging
import threading
import requests
import functools
from requests.utils import to_native_string
from . import statsd
from .util import parse_url
from . import request_id

__all__ = [
    'HEADER',
    'get_session',
    'configure',
    'enable_requests_logging',
]

HEADER = to_native_string(request_id.HEADER)
storage = threading.local()
storage.sessions = {}


def get_session(cls=requests.Session):
    session = storage.sessions.get(cls)
    if session is None:
        session = storage.sessions[cls] = cls()
        configure(session)
    return session


def configure(session):
    # insert metrics hook first as it needs response, and does't
    # alter hook_data for later hooks
    if metrics_response_hook not in session.hooks['response']:
        session.hooks['response'].insert(0, metrics_response_hook)
    # for some reason, requests doesn't have a pre_request hook anymore
    # so, we do something horrible - we decorate the *instance* method
    # this allows us to inject request id into the request, but without
    # requiring a particular subclass of Session, leaving the user free to use
    # whatever, but still use talisker's enhancements.
    # If requests ever regains request hooks, this can go away
    # If anyone has a better solution, *please* tell me!
    if not hasattr(session.prepare_request, '_inject_request_id'):
        session.prepare_request = inject_request_id(session.prepare_request)


def inject_request_id(func):
    @functools.wraps(func)
    def prepare_request(request):
        prepared = func(request)
        id = request_id.get()
        if id and HEADER not in prepared.headers:
            prepared.headers[HEADER] = id
        return prepared
    prepare_request._inject_request_id = True
    return prepare_request


def metrics_response_hook(response, **kwargs):
    """Response hook that records statsd metrics"""
    prefix, duration = get_timing(response)
    statsd.get_client().timing(prefix, duration)


def get_timing(response):
    parsed = parse_url(response.request.url)
    duration = response.elapsed.total_seconds() * 1000
    prefix = 'requests.{}.{}.{}'.format(
        parsed.hostname.replace('.', '-'),
        response.request.method.upper(),
        str(response.status_code),
    )
    return prefix, duration


def enable_requests_logging():  # pragma: nocover
    """Full requests debug output is tricky to enable"""
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 1
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
