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

import collections
import functools
import logging
import threading
import warnings

from future.moves.urllib.parse import parse_qsl
from future.utils import text_to_native_str
import raven.breadcrumbs
import requests
import werkzeug.local

from talisker.context import track_request_metric
from talisker import request_id
import talisker.metrics
from talisker.util import (
    context_local,
    get_errno_fields,
    module_dict,
    parse_url,
)

__all__ = [
    'configure',
    'enable_requests_logging',
    'get_session',
    'register_endpoint_name',
]

# wsgi requires native strings
HEADER = text_to_native_str(request_id.HEADER)

STORAGE = threading.local()
STORAGE.sessions = {}
HOSTS = module_dict()
_local = context_local()


def clear():
    if hasattr(STORAGE, 'sessions'):
        STORAGE.sessions.clear()
    HOSTS.clear()
    werkzeug.local.release_local(_local)


# storage for metric url state, as requests design allows for no other way
logger = logging.getLogger('talisker.requests')


class RequestsMetric:
    latency = talisker.metrics.Histogram(
        name='requests_latency',
        documentation='Duration of http calls via requests library',
        labelnames=['host', 'view', 'status'],
        statsd='{name}.{host}.{view}.{status}',
    )

    count = talisker.metrics.Counter(
        name='requests_count',
        documentation='Count of http calls via requests library',
        labelnames=['host', 'view'],
        statsd='{name}.{host}.{view}',
    )

    errors = talisker.metrics.Counter(
        name='requests_errors',
        documentation='Count of errors in responses via requests library',
        labelnames=['host', 'type', 'view', 'status'],
        statsd='{name}.{host}.{type}.{view}.{status}',
    )


def register_endpoint_name(endpoint, name):
    """Register a human friendly name for an IP:PORT address for metrics."""
    parsed = parse_url(endpoint)
    HOSTS[parsed.netloc] = name


# backwards compat alias
def register_ip(ip, name):
    warnings.warn(
        "Please use register_endpoint_name", warnings.DeprecationWarning)
    register_endpoint_name(ip, name)


def get_endpoint_name(endpoint):
    parsed = parse_url(endpoint)
    return HOSTS.get(parsed.netloc)


def get_session(cls=requests.Session):
    if not hasattr(STORAGE, 'sessions'):
        STORAGE.sessions = {}
    session = STORAGE.sessions.get(cls)
    if session is None:
        session = STORAGE.sessions[cls] = cls()
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
    if not hasattr(session.send, '_send_wrapper'):
        session.send = send_wrapper(session.send)
    if not hasattr(session.request, '_request_wrapper'):
        session.request = request_wrapper(session.request)


def send_wrapper(func):
    """Sets header and records exception details."""
    @functools.wraps(func)
    def send(request, **kwargs):
        rid = request_id.get()
        if rid and HEADER not in request.headers:
            request.headers[HEADER] = rid
        try:
            return func(request, **kwargs)
        except Exception as e:
            record_request(request, None, e)
            raise

    send._send_wrapper = True
    return send


def request_wrapper(func):
    """Adds support for metric_name kwarg to session."""
    @functools.wraps(func)
    def request(method, url, **kwargs):
        try:
            _local.metric_api_name = kwargs.pop('metric_api_name', None)
            _local.metric_host_name = kwargs.pop('metric_host_name', None)
            return func(method, url, **kwargs)
        finally:
            del _local.metric_api_name
            del _local.metric_host_name
    request._request_wrapper = True
    return request


def collect_metadata(request, response):
    metadata = collections.OrderedDict()

    parsed = parse_url(request.url)

    hostname = get_endpoint_name(request.url)
    if hostname is None:
        address = parsed.netloc
        hostname = parsed.hostname
    else:
        address = hostname
        if parsed.port:
            address += ':{}'.format(parsed.port)

    # do not include querystring in url, as may have senstive info
    metadata['url'] = '{}://{}{}'.format(parsed.scheme, address, parsed.path)
    if parsed.query:
        metadata['url'] += '?'
        redacted = ('{}=<len {}>'.format(k, len(v))
                    for k, v in parse_qsl(parsed.query))
        metadata['qs'] = '?' + '&'.join(redacted)
        metadata['qs_size'] = len(parsed.query)

    metadata['method'] = request.method
    metadata['host'] = hostname
    if parsed.netloc not in metadata['url']:
        metadata['netloc'] = parsed.netloc

    if response is not None:
        metadata['status_code'] = response.status_code

        if 'X-View-Name' in response.headers:
            metadata['view'] = response.headers['X-View-Name']
        if 'Server' in response.headers:
            metadata['server'] = response.headers['Server']
        duration = response.elapsed.total_seconds() * 1000
        metadata['duration_ms'] = round(duration, 3)

    request_type = request.headers.get('content-type', None)
    if request_type is not None:
        metadata['request_type'] = request_type

    if metadata['method'] in ('POST', 'PUT', 'PATCH'):
        try:
            metadata['request_size'] = int(
                request.headers.get('content-length', 0))
        except ValueError:
            pass

    if response is not None:
        response_type = response.headers.get('content-type', None)
        if response_type is not None:
            metadata['response_type'] = response_type
        try:
            metadata['response_size'] = int(
                response.headers.get('content-length', 0))
        except ValueError:
            pass

    return metadata


def metrics_response_hook(response, **kwargs):
    """Response hook that records statsd metrics and breadcrumbs."""
    try:
        record_request(response.request, response)
    except Exception:
        logging.exception('response hook error')


def record_request(request, response=None, exc=None):
    metadata = collect_metadata(request, response)
    if response:
        track_request_metric('http', metadata['duration_ms'])

    if exc:
        metadata.update(get_errno_fields(exc))

    raven.breadcrumbs.record(
        type='http',
        category='requests',
        data=metadata,
    )

    labels = {
        'host': metadata['host'],
        'view': metadata.get('view', 'unknown'),
    }

    metric_api_name = getattr(_local, 'metric_api_name', None)
    metric_host_name = getattr(_local, 'metric_host_name', None)
    if metric_api_name is not None:
        labels['view'] = metric_api_name
    if metric_host_name is not None:
        labels['host'] = metric_host_name
    labels['host'] = labels['host'].replace('.', '-')

    RequestsMetric.count.inc(**labels)

    if response is None:
        # likely connection errors
        logger.exception('http request failure', extra=metadata)
        labels['type'] = 'connection'
        labels['status'] = metadata.get('errno', 'unknown')
        RequestsMetric.errors.inc(**labels)
    else:
        logger.info('http request', extra=metadata)
        labels['status'] = metadata['status_code']
        RequestsMetric.latency.observe(metadata['duration_ms'], **labels)
        if metadata['status_code'] >= 500:
            labels['type'] = 'http'
            RequestsMetric.errors.inc(**labels)


def enable_requests_logging():  # pragma: nocover
    """Full requests debug output is tricky to enable"""
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 1
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
