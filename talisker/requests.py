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
from datetime import datetime
import functools
import itertools
import logging
import random
import warnings
import time
from future.moves.urllib.parse import (
    parse_qsl,
    urlparse,
    urlsplit,
    urlunsplit,
)

import future.utils
import requests
from requests.adapters import HTTPAdapter
import requests.exceptions
from requests.utils import should_bypass_proxies
import urllib3.exceptions
from urllib3.util import Retry

import talisker
from talisker import Context
import talisker.metrics
from talisker.util import (
    get_errno_fields,
    module_dict,
    parse_url,
    Local,
)

__all__ = [
    'configure',
    'enable_requests_logging',
    'get_session',
    'register_endpoint_name',
]


STORAGE = Local()
STORAGE.sessions = {}
HOSTS = module_dict()
DEBUG_HEADER = future.utils.text_to_native_str('X-Debug')


def clear():
    if hasattr(STORAGE, 'sessions'):
        STORAGE.sessions.clear()
    HOSTS.clear()


# storage for metric url state, as requests design allows for no other way
logger = logging.getLogger('talisker.requests')


class RequestsMetric:
    latency = talisker.metrics.Histogram(
        name='requests_latency',
        documentation='Duration of http calls via requests library',
        labelnames=['host', 'view', 'status'],
        statsd='{name}.{host}.{view}.{status}',
        # predefining these sucks
        buckets=[4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192],
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
    config = talisker.get_config()

    @functools.wraps(func)
    def send(request, **kwargs):
        rid = Context.request_id
        if rid and config.id_header not in request.headers:
            request.headers[config.id_header] = rid
        ctx_deadline = Context.current().deadline
        if ctx_deadline:
            deadline = datetime.utcfromtimestamp(ctx_deadline)
            formatted = deadline.isoformat() + 'Z'
            request.headers[config.deadline_header] = formatted
        if Context.debug:
            request.headers[DEBUG_HEADER] = '1'
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
        ctx = Context.current()
        try:
            ctx.metric_api_name = kwargs.pop('metric_api_name', None)
            ctx.metric_host_name = kwargs.pop('metric_host_name', None)
            return func(method, url, **kwargs)
        finally:
            # some requests errors can cause the context to be lost, and we
            # should never fail due to this.
            try:
                del ctx.metric_api_name
                del ctx.metric_host_name
            except Exception:
                pass
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
        Context.track('http', metadata['duration_ms'])

    if exc:
        metadata.update(get_errno_fields(exc))

    talisker.sentry.record_breadcrumb(
        type='http',
        category='requests',
        data=metadata,
    )

    labels = {
        'host': metadata['host'],
        'view': metadata.get('view', 'unknown'),
    }

    ctx = Context.current()
    metric_api_name = getattr(ctx, 'metric_api_name', None)
    metric_host_name = getattr(ctx, 'metric_host_name', None)
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


class TaliskerAdapter(HTTPAdapter):

    KNOWN_SCHEMES = ('http', 'https')

    def __init__(self, backends=None, backend_iter=None, connect=1.0,
                 read=10.0, max_retries=0, *args, **kwargs):
        # set up backends
        self.connect_timeout = connect
        self.read_timeout = read

        if max_retries == 0:
            self.__retry = None
        elif isinstance(max_retries, int):
            self.__retry = Retry.from_int(max_retries)
        else:
            self.__retry = max_retries

        if backend_iter is not None:
            if backends is not None:
                raise ValueError('can not set both backends and backend_iter')
            self.backend_iter = backend_iter
        elif backends is not None:
            self.backend_iter = self._create_backend_iterable(backends)
        else:
            self.backend_iter = None

        # disable lower level urllib3 retries completely
        kwargs['max_retries'] = Retry(0, read=False)
        super().__init__(*args, **kwargs)

    def _create_backend_iterable(self, backends):

        def _validate(backend):
            if '://' not in backend:
                raise ValueError('backend url must include scheme: {}'.format(
                    backend))
            scheme = urlparse(backend).scheme
            if scheme not in self.KNOWN_SCHEMES:
                raise ValueError('backend url must be one of {}'.format(
                    self.KNOWN_SCHEMES))
            return scheme

        # makes a copy and also forces any generators to a list
        backends = list(backends)
        schemes = set(_validate(backend) for backend in backends)
        if len(schemes) != 1:
            raise ValueError(
                'mixed url schemes not supported: {}'.format(
                    ','.join(backends)
                )
            )
        random.shuffle(backends)
        return itertools.cycle(backends)

    def select_backend(self, request):
        """Replaces the scheme and netloc of the url with the backend"""
        if self.backend_iter is None:
            return
        next_backend = next(self.backend_iter)
        scheme, netloc = urlsplit(next_backend)[0:2]
        parsed = urlsplit(request._original_url)
        request.url = urlunsplit(parsed._replace(scheme=scheme, netloc=netloc))

    def calculate_timeouts(self, request, timeout):
        connect, read = timeout
        elapsed = time.time() - request._start
        budget_left = max(0, request._read_timeout - elapsed)
        return (min(connect, budget_left), min(read, budget_left))

    def modify_send_kwargs_for_request(self, request, send_kwargs):
        # This approach does not cover some (hopefully rare) cases:
        # * If the mount point url is in the no_proxy list the proxy config
        #   will have already been removed.
        # * If the mount point url and backend url match different proxy
        #   authorisation the one for the mount point url will be used.
        # However the code to do this the right way is on the session and not
        # easily reproducable here.
        proxies = send_kwargs.get('proxies')
        if proxies:
            if request.url != request._original_url:
                if should_bypass_proxies(request.url, proxies.get('no')):
                    send_kwargs = send_kwargs.copy()
                    send_kwargs['proxies'] = {}
        return send_kwargs

    def send(self, request, *args, **kwargs):
        # ensure both connect and read timeouts set
        request._original_url = request.url
        retry = self.__retry
        connect, read = self.connect_timeout, self.read_timeout
        timeout = kwargs.pop('timeout', None)
        if timeout:
            # timeout can be one of:
            #  - number
            #  - Retry
            #  - (number, Retry)
            #  - (number, number)
            #  - (number, number, Retry)
            if isinstance(timeout, (int, float)):
                read = self.connect_timeout
            elif isinstance(timeout, Retry):
                retry = timeout
            else:
                try:
                    if isinstance(timeout[-1], urllib3.Retry):
                        retry = timeout[-1]
                        timeout = timeout[:-1]
                    size = len(timeout)
                    assert size in (1, 2)
                    if size == 1:
                        read = timeout[0]
                    elif size == 2:
                        connect, read = timeout
                except Exception:
                    raise ValueError(
                        'timeout must be a float/int, None, urllib3.Retry, '
                        'or a tuple of either two float/ints, '
                        'or two float/ints and a urllib3.Retry'
                    )

        # enforce any context deadline
        ctx_timeout = Context.deadline_timeout()
        if ctx_timeout is not None:
            connect = min(connect, ctx_timeout)
            read = min(read, ctx_timeout)

        # ensure urllib3 timeout
        kwargs['timeout'] = (connect, read)

        # load balance the url
        self.select_backend(request)

        # if no retry, just pass straight to base class
        if retry is None:
            return super().send(
                request,
                *args,
                **self.modify_send_kwargs_for_request(request, kwargs)
            )

        request._retry = retry.new()
        request._start = time.time()
        request._read_timeout = read
        return self._send(request, *args, **kwargs)

    def _send(self, request, *args, **kwargs):
        response = None
        try:
            response = super().send(
                request,
                *args,
                **self.modify_send_kwargs_for_request(request, kwargs)
            )
        except requests.ConnectionError as exc:
            retries_exhausted = False

            error = exc.args[0]
            if isinstance(error, urllib3.exceptions.MaxRetryError):
                # we need the original urllib3 exception base error
                error = error.reason
            try:
                request._retry = request._retry.increment(
                    request.method,
                    request.url,
                    error=error,
                )
            except urllib3.exceptions.MaxRetryError:
                retries_exhausted = True
                # we catch and flag to reraise the original exception.
                # This avoids confusing the already lengthy exception chain
            except Exception as urllib3_exc:
                if isinstance(urllib3_exc, error.__class__):
                    # underlying urllib3 reraised, no more retries
                    retries_exhausted = True
                else:
                    raise

            if retries_exhausted:
                # An interesting bit of py2/3 differences here. We want to
                # reraise the original ConnectionError, with context unaltered.
                # A naked raise does exactly this in py3, it reraises the
                # exception that caused the current except: block.  But in py2,
                # naked raise would raise the *last* error, MaxRetryError,
                # which we do not want. So we explicitly reraise the original
                # ConnectionError. In py3, this would not be desirable, as the
                # exception context would be confused, by py2 does not do
                # chained exceptions, so, erm, yay?
                if future.utils.PY3:
                    raise  # raises the original ConnectionError
                else:
                    raise exc

            # we are going to retry, so backoff as appropriate
            request._retry.sleep()

        else:
            # We got a response, but perhaps we need to retry
            #
            # Note: urllib3 retry logic handles redirects here, but we do not
            # as requests explicitly does not use it (it calls urlopen with
            # redirect=False)
            #
            has_retry_after = 'Retry-After' in response.headers
            if request._retry.is_retry(
                    request.method,
                    response.status_code,
                    has_retry_after):
                # response allows for retry, but perhaps we are exhausted
                try:
                    request._retry = request._retry.increment(
                        request.method,
                        request.url,
                        response=response.raw,
                    )
                except urllib3.exceptions.MaxRetryError as e:
                    if request._retry.raise_on_status:
                        # manually wrap it in a requests exception
                        raise requests.exceptions.RetryError(
                            e, request=request)
                    return response

                request._retry.sleep(response.raw)
            else:
                return response

        # let's retry, with load balancing and adjusted timeouts
        self.select_backend(request)
        (connect, read) = self.calculate_timeouts(request, kwargs['timeout'])
        if read <= 0:
            raise requests.ReadTimeout(request=request, response=response)
        kwargs['timeout'] = (connect, read)
        return self._send(request, *args, **kwargs)
