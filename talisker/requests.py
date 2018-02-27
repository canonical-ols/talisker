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

import functools
import logging
import threading

from future.utils import native
import requests
import werkzeug.local

from . import statsd
from .util import parse_url
from . import request_id

__all__ = [
    'configure',
    'enable_requests_logging',
    'get_session',
    'register_ip',
]

# wsgi requires native strings
HEADER = native(request_id.HEADER)
storage = threading.local()
storage.sessions = {}
HOSTS = {}

# storage for metric url state, as requests design allows for no other way
_local = werkzeug.local.Local()


def register_ip(ip, name):
    """Register a human friendly name for an IP address for metrics."""
    HOSTS[ip] = name


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
    # so, we do something horrible - we decorate some *instance* methods of the
    # session. This allows us to support injecting request id into the request,
    # and allow a good api for customising the emitted metrics. But it does not
    # require a particular subclass of Session, leaving the user free to use
    # whatever, but still use talisker's enhancements.
    # If requests ever regains request hooks, then maybe this can go away
    # If anyone has a better solution, *please* tell me!
    if not hasattr(session.send, '_inject_request_id'):
        session.send = inject_request_id(session.send)
    if not hasattr(session.request, '_metric_path_len'):
        session.request = enable_metric_path_len(session.request)


def inject_request_id(func):
    @functools.wraps(func)
    def send(request, **kwargs):
        id = request_id.get()
        if id and HEADER not in request.headers:
            request.headers[HEADER] = id
        return func(request, **kwargs)
    send._inject_request_id = True
    return send


def enable_metric_path_len(func):
    @functools.wraps(func)
    def request(method, url, **kwargs):
        try:
            _local.metric_path_len = kwargs.pop('metric_path_len', 0)
            return func(method, url, **kwargs)
        finally:
            del _local.metric_path_len
    request._metric_path_len = True
    return request


def metrics_response_hook(response, **kwargs):
    """Response hook that records statsd metrics"""
    path_len = getattr(_local, 'metric_path_len', 0)
    prefix, duration = get_timing(response, path_len)
    statsd.get_client().timing(prefix, duration)


def get_timing(response, path_len=0):
    parsed = parse_url(response.request.url)
    duration = response.elapsed.total_seconds() * 1000
    if parsed.hostname in HOSTS:
        hostname = HOSTS[parsed.hostname]
    else:
        hostname = parsed.hostname
    if path_len > 0:
        path_components = parsed.path.lstrip('/').split('/')
        dotted_path = '.'.join(path_components[:path_len])
        url_components = '{}.'.format(dotted_path)
    else:
        url_components = ''

    prefix = 'requests.{}.{}{}.{}'.format(
        hostname.replace('.', '-'),
        url_components,
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
