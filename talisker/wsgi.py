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


from collections import OrderedDict
from datetime import datetime
import logging
import os
import time
import traceback
import sys
import uuid

from talisker.context import Context
import talisker.endpoints
import talisker.requests
import talisker.statsd
from talisker.util import set_wsgi_header, datetime_to_timestamp
from talisker.render import (
    Content,
    Table,
    PreformattedText,
    render_best_content_type,
)


logger = logging.getLogger('talisker.wsgi')

__all__ = [
    'TaliskerMiddleware',
    'wrap',
]

# track in-flight requests for this worker process, allows use to still log
# them in the case of timeouts and other issues
REQUESTS = {}


class RequestTimeout(Exception):
    pass


def talisker_error_response(environ, headers, exc_info):
    """Returns WSGI iterable to be returned as an error response.

    This error response uses Talisker's built in rendering support to be able
    to render content in json (default), html, or text.

    Returns a tuple of (content_type, iterable)."""
    exc_type, exc, tb = exc_info
    config = talisker.get_config()
    tb = Content('[traceback hidden]', tag='p', id='traceback')

    rid = environ['REQUEST_ID']
    id_info = [('Request-Id', rid)]

    wsgi_environ = []
    request_headers = []

    for k, v in environ.items():
        if k.startswith('HTTP_'):
            request_headers.append((k[5:].replace('_', '-').title(), v))
        else:
            wsgi_environ.append((k, v))

    if config.devel:
        title = '{}: {}'.format(exc_type.__name__, exc)
        lines = traceback.format_exception(*exc_info)
        tb = PreformattedText(''.join(lines), id='traceback')
    else:
        title = 'Server Error: {}'.format(exc_type.__name__)

    content = [
        Content(title, tag='h1', id='title'),
        Table(id_info, id='id'),
        tb,
        Table(
            sorted(request_headers),
            id='request_headers',
            headers=['Request Headers', ''],
        ),
        Table(
            sorted(wsgi_environ),
            id='wsgi_env',
            headers=['WSGI Environ', ''],
        ),
        Table(
            headers,
            id='response_headers',
            headers=['Response Headers', ''],
        ),
    ]

    return render_best_content_type(environ, title, content)


_error_response_handler = talisker_error_response


def set_error_response_handler(func):
    global _error_response_handler
    _error_response_handler = func


class WSGIMetric:
    latency = talisker.metrics.Histogram(
        name='wsgi_latency',
        documentation='Duration of requests served by WSGI',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
        buckets=[4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192],
    )

    requests = talisker.metrics.Counter(
        name='wsgi_requests',
        documentation='Count of WSGI requests',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )

    errors = talisker.metrics.Counter(
        name='wsgi_errors',
        documentation='Count of WSGI errors',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )

    timeouts = talisker.metrics.Counter(
        name='wsgi_timeouts',
        documentation='Count of WSGI timeout',
        labelnames=['view', 'method'],
        statsd='{name}.{view}.{method}',
    )


class TaliskerWSGIRequest():
    """Container for WSGI request/response cycle.

    It provides a start_response function that adds some headers, and captures
    the start_response arguments. It can then wrap a WSGI response iterator in
    order to count the content-length and log the response.
    """

    def __init__(self,
                 environ,
                 start_response,
                 added_headers=None):

        # request metadata
        self.environ = environ
        self.original_start_response = start_response
        self.added_headers = added_headers

        # response metadata
        self.status = None
        self.headers = []
        self.exc_info = None
        self.iter = None
        self.status_code = 0
        self.content_length = 0
        self.file_path = None
        self.closed = False
        self.start_response_called = False
        self.start_response_timestamp = None
        self.duration = 0
        self.timedout = False

    def start_response(self, status, headers, exc_info=None):
        """Adds response headers and stores response data.

        Does not directly call upstream start_response - that is done upon
        iteration, to provide more control over status/headers in the case of
        an error.
        """
        if self.start_response_timestamp is None:
            self.start_response_timestamp = time.time()

        if self.added_headers:
            for header, value in self.added_headers.items():
                set_wsgi_header(headers, header, value)

        if 'REQUEST_ID' in self.environ:
            # set id header on outgoing response
            config = talisker.get_config()
            set_wsgi_header(
                headers,
                config.id_header,
                self.environ['REQUEST_ID'],
            )

        # are we going to be sending a sentry report? If so, include header
        if self.exc_info or Context.debug:
            set_wsgi_header(headers, 'X-Sentry-Id', self.environ['SENTRY_ID'])

        self.status = status
        status_code, _, _ = status.partition(' ')
        self.status_code = int(status_code)
        self.headers = headers
        self.exc_info = exc_info

    def call_start_response(self):
        self.original_start_response(
            self.status,
            self.headers,
            self.exc_info,
        )
        self.start_response_called = True

    def wrap_response(self, response_iter):
        """Transforms this instance into an iterator that wraps the response.

        Allows for error handling and tracking response size.
        """
        wrapper = self.environ.get('wsgi.file_wrapper')
        if wrapper and isinstance(response_iter, wrapper):
            # attempt to gather some metadata about the file for logging
            filelike = getattr(response_iter, 'filelike', None)
            if filelike:
                self.file_path = getattr(filelike, 'name', None)
                try:
                    self.content_length = os.fstat(filelike.fileno()).st_size
                except Exception:
                    pass

            # we can not wrap this, or we break sendfile optimisations in the
            # server. But we do want to log it, so we patch its close method.
            original_close = getattr(response_iter, 'close', lambda: None)

            def close():
                original_close()
                self.finish_request()
            response_iter.close = close

            # because we are not wrapping, we need to call start response now
            self.call_start_response()

            return response_iter
        else:
            self.iter = iter(response_iter)
            return self

    def __iter__(self):
        return self

    def __next__(self):
        """Wraps the provided WSGI content iterator.

        It counts the bytes returned, as well attempting to handle any errors
        thrown by the iterator.

        """
        if self.iter is None:
            raise Exception("iterator has not been set yet")
        # We don't actually call the WSGI server's provided start_response
        # until we are ready to start iterating the content. This provides us
        # with more control over the response, and allows us to more cleanly
        # switch to an error response regardless of WSGI server implementation.
        # Talisker apps can call start_response multiple times, and only the
        # final call will influence the response status and headers. In
        # Gunicorn for example, the headers from all calls to start_response
        # would be sent, which usually not correct, and leads to duplictation
        # or conflict of headers

        # There is some finesse here around calling start_response(), to
        # support different behaviours from our wrapped WSGI app. Most WSGI
        # apps call start_response() before returning their iterator, and
        # indeed must do that if they have an empty iterator.
        #
        # Other apps can be lazy, and do not call start_response() until their
        # iterator is started (e.g. werkzeug's DebuggedApplication).
        # So we try calling start_response() just *before* iteration, as well
        # as also after the first iteration, to work with both models.
        if self.status is not None and not self.start_response_called:
            self.call_start_response()
        try:
            try:
                chunk = next(self.iter)
                # support lazy WSGI apps, as above
                if not self.start_response_called:
                    self.call_start_response()
            except (StopIteration, GeneratorExit):
                # support lazy WSGI apps with no content
                if not self.start_response_called:
                    self.call_start_response()
                raise
            except Exception as e:
                self.exc_info = sys.exc_info()
                if isinstance(e, RequestTimeout):
                    self.timedout = True
                # switch to generating an error response
                self.iter = iter(self.error(self.exc_info))
                chunk = next(self.iter)
            except SystemExit as e:
                if e.code != 0:
                    self.exc_info = sys.exc_info()
                raise
        except (Exception, SystemExit):
            # If the above has raised, it means that the request is done,
            # While WSGI servers will call .close() on the iterator, middleware
            # that wraps the iterator may not, so we call close manually.
            self.close()
            raise

        self.content_length += len(chunk)
        return chunk

    # py2 compat
    def next(self):
        return self.__next__()

    def error(self, exc_info):
        """Generate a WSGI response describing the error."""
        content_type, body = _error_response_handler(
            self.environ,
            self.headers,
            exc_info,
        )

        self.start_response(
            '500 Internal Server Error',
            [('Content-Type', content_type)],
            exc_info,
        )
        # Note: the original start_response should raise if headers have been
        # sent, which should bubble up to the WSGI server.

        self.call_start_response()
        return [body]

    def close(self):
        """Close and record the response."""
        if self.closed:
            return

        try:
            iter_close = getattr(self.iter, 'close', None)
            if iter_close:
                iter_close()
        finally:
            self.finish_request()
            self.closed = True

    def finish_request(self, timeout=False):
        if timeout:
            self.timedout = timeout
        start = self.environ.get('start_time')
        response_latency = 0
        if start:
            self.duration = time.time() - start
            if self.start_response_timestamp:
                response_latency = (
                    (self.start_response_timestamp - start) * 1000
                )

        metadata = self.get_metadata()
        self.log(metadata)
        self.metrics(metadata)

        # We want to send a sentry report if:
        # a) an error or timeout occured
        # b) soft timeout
        # c) manual debugging

        if talisker.sentry.enabled:
            soft_timeout = Context.soft_timeout
            try:
                if self.exc_info:
                    self.send_sentry(metadata)
                elif Context.debug:
                    self.send_sentry(
                        metadata,
                        msg='Debug: {}'.format(metadata['path']),
                        level='debug',
                    )
                elif soft_timeout > 0 and response_latency > soft_timeout:
                    self.send_sentry(
                        metadata,
                        msg='Soft Timeout: {}'.format(metadata['path']),
                        level='warning',
                        extra={
                            'start_response_latency': response_latency,
                            'soft_timeout': soft_timeout,
                        },
                    )
            except Exception:
                logger.exception('failed to send soft timeout report')

        talisker.clear_context()
        rid = self.environ.get('REQUEST_ID')
        if rid:
            REQUESTS.pop(rid, None)

    def get_metadata(self):
        """Return an ordered dictionary of request metadata for logging."""
        environ = self.environ
        extra = OrderedDict()

        if self.headers is None:
            headers = {}
        else:
            headers = dict((k.lower(), v) for k, v in self.headers)

        extra['method'] = environ.get('REQUEST_METHOD')
        script = environ.get('SCRIPT_NAME', '')
        path = environ.get('PATH_INFO', '')
        extra['path'] = script + '/' + path.lstrip('/')
        qs = environ.get('QUERY_STRING')
        if qs:
            extra['qs'] = environ.get('QUERY_STRING')
        if self.status_code:
            extra['status'] = self.status_code
        if 'VIEW_NAME' in environ:
            extra['view'] = environ['VIEW_NAME']
        elif 'x-view-name' in headers:
            extra['view'] = headers['x-view-name']
        extra['duration_ms'] = round(self.duration * 1000, 3)
        extra['ip'] = environ.get('REMOTE_ADDR', None)
        extra['proto'] = environ.get('SERVER_PROTOCOL')
        if self.content_length:
            extra['length'] = self.content_length
        if self.file_path is not None:
            extra['filepath'] = self.file_path
        request_length = environ.get('CONTENT_LENGTH')
        if request_length:
            try:
                extra['request_length'] = int(request_length)
            except ValueError:
                pass
        content_type = environ.get('CONTENT_TYPE')
        if content_type:
            extra['request_type'] = content_type
        referrer = environ.get('HTTP_REFERER', None)
        if referrer is not None:
            extra['referrer'] = environ.get('HTTP_REFERER', None)
        if 'HTTP_X_FORWARDED_FOR' in environ:
            extra['forwarded'] = environ['HTTP_X_FORWARDED_FOR']
        if 'HTTP_USER_AGENT' in environ:
            extra['ua'] = environ['HTTP_USER_AGENT']

        if self.timedout:
            extra['timeout'] = True

        if self.exc_info and self.exc_info[0]:
            extra['exc_type'] = str(self.exc_info[0].__name__)
            extra['trailer'] = ''.join(
                traceback.format_exception(*self.exc_info)
            )

        tracking = Context.current().tracking
        for name, tracker in sorted(tracking.items()):
            extra[name + '_count'] = tracker.count
            extra[name + '_time_ms'] = tracker.time

        return extra

    def log(self, extra):
        """Log a WSGI request.

        Similar to access logs, but structured and with more data."""
        try:
            msg = "{method} {path}{0}".format(
                '?' if 'qs' in extra else '',
                **extra
            )
        except Exception:
            logger.exception('error generating access log', extra=extra)
        else:
            logger.info(msg, extra=extra)

    def metrics(self, extra):
        labels = {
            'view': extra.get('view', 'unknown'),
            'method': extra['method'],
            'status': str(extra.get('status', 'timeout')).lower(),
        }

        WSGIMetric.requests.inc(**labels)
        WSGIMetric.latency.observe(extra['duration_ms'], **labels)
        if self.timedout:
            lbls = labels.copy()
            lbls.pop('status')
            WSGIMetric.timeouts.inc(**lbls)
        elif self.status_code and self.status_code >= 500:
            WSGIMetric.errors.inc(**labels)

    def send_sentry(self, metadata, msg=None, data=None, **kwargs):
        from raven.utils.wsgi import get_current_url, get_environ, get_headers
        if data is None:
            data = {}
        if 'SENTRY_ID' in self.environ:
            data['event_id'] = self.environ['SENTRY_ID']
        # sentry displays these specific fields in a different way
        http_context = {
            'url': get_current_url(self.environ),
            # we don't use the sanitized version from metadata, we want the
            # real query string
            'query_string': self.environ.get('QUERY_STRING'),
            'method': metadata['method'],
            'headers': dict(get_headers(self.environ)),
            'env': dict(get_environ(self.environ)),
        }
        talisker.sentry.report_wsgi(
            http_context,
            exc_info=self.exc_info,
            msg=msg,
            data=data,
            **kwargs
        )


class TaliskerMiddleware():
    """Talisker entrypoint for WSGI apps.

    Sets up some values in environ, handles errors, and wraps responses in
    TaliskerWSGIRequest.
    """
    def __init__(self, app, environ=None, headers=None):

        """Configure talisker middleware.

         - app: the wsgi app
         - environ: things to put in the environment
         - headers: additional headers to to add
        """
        self.app = app
        self.environ = environ
        self.headers = headers

        # ensure new workers have an initialised sentry_context
        talisker.sentry.new_context()

    def __call__(self, environ, start_response):
        Context.new()
        config = talisker.get_config()

        # setup environment
        environ['start_time'] = Context.current().start_time
        if self.environ:
            environ.update(self.environ)
        # ensure request id
        if config.wsgi_id_header not in environ:
            environ[config.wsgi_id_header] = str(uuid.uuid4())
        rid = environ[config.wsgi_id_header]
        environ['REQUEST_ID'] = rid
        # needs to be different from request id, as request can be passed on to
        # upstream services
        environ['SENTRY_ID'] = uuid.uuid4().hex

        Context.request_id = rid
        Context.soft_timeout = config.soft_request_timeout

        # calculate ip route
        route = None
        try:
            forwarded = environ.get('HTTP_X_FORWARDED_FOR')
            if forwarded:
                route = [a.strip() for a in forwarded.split(',')]
            elif "REMOTE_ADDR" in environ:
                route = [environ["REMOTE_ADDR"]]
        except Exception as e:
            logger.exception(e)
        else:
            if route is not None:
                environ['ACCESS_ROUTE'] = route
                environ['CLIENT_ADDR'] = route[-1]

        if 'HTTP_X_DEBUG' in environ:
            if config.is_trusted_addr(environ.get('CLIENT_ADDR')):
                Context.set_debug()
            else:
                logger.warning(
                    'X-Debug header set but not trusted IP address',
                    extra={
                        "access_route": ','.join(environ.get('ACCESS_ROUTE')),
                        "x_debug": environ['HTTP_X_DEBUG'],
                    }
                )

        set_deadline = False
        header_deadline = environ.get('HTTP_X_REQUEST_DEADLINE')
        if header_deadline:
            try:
                deadline = datetime.strptime(
                    header_deadline,
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                )
            except ValueError:
                pass
            else:
                # set deadline directly
                # TODO: validate deadline is in future?
                Context.set_absolute_deadline(datetime_to_timestamp(deadline))
                set_deadline = True

        if not set_deadline and config.request_timeout is not None:
            Context.set_relative_deadline(config.request_timeout)

        # create the response container
        request = TaliskerWSGIRequest(environ, start_response, self.headers)

        # track in-flight requests
        if rid in REQUESTS:
            logger.warning(
                'duplicate request id received by gunicorn worker',
                extra={'request_id': rid}
            )
        else:
            REQUESTS[rid] = request

        try:
            response_iter = self.app(environ, request.start_response)
        except Exception as e:
            # store details for later
            request.exc_info = sys.exc_info()
            if isinstance(e, RequestTimeout):
                request.timedout = True
            # switch to generating an error response
            response_iter = request.error(request.exc_info)
        except SystemExit as e:
            if e.code != 0:
                request.exc_info = sys.exc_info()
                request.finish_request()
            raise

        return request.wrap_response(response_iter)


def wrap(app):
    """Wraps a WSGI api in Talisker middleware."""
    if getattr(app, '_talisker_wrapped', False):
        return app

    config = talisker.config.get_config()
    environ = {
        'statsd': talisker.statsd.get_client(),
        'requests': talisker.requests.get_session(),
    }
    headers = {'X-VCS-Revision': config.revision_id}

    wrapped = app
    # added in reverse order
    wrapped = talisker.endpoints.StandardEndpointMiddleware(wrapped)
    wrapped = TaliskerMiddleware(wrapped, environ, headers)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
