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
import logging
import os
import time
import traceback
import sys

import talisker.context
import talisker.endpoints
import talisker.requests
import talisker.request_id
import talisker.statsd
from talisker.util import set_wsgi_header
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


def talisker_error_response(environ, headers, exc_info):
    """Returns WSGI iterable to be returned as an error response

    Returns a tuple of (content_type, iterable)."""
    exc_type, exc, tb = exc_info
    config = talisker.get_config()
    tb = Content('[traceback hidden]', tag='p', id='traceback')

    rid = environ['REQUEST_ID']
    id_info = [('Request-Id', rid)]
    sentry_id = environ.get('SENTRY_ID')
    if sentry_id:
        id_info.append(('Sentry-ID', sentry_id))

    wsgi_environ = []
    request_headers = []

    for k, v in environ.items():
        if k.startswith('HTTP_'):
            request_headers.append((k[5:].replace('_', '-').title(), v))
        else:
            wsgi_environ.append((k, v))

    if config.devel:
        title = 'Request {}: {}'.format(rid, exc)
        lines = traceback.format_exception(*exc_info)
        tb = PreformattedText(''.join(lines), id='traceback')
    else:
        title = 'Request {}: {}'.format(rid, exc_type.__name__)

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


class WSGIResponse():
    """Container for WSGI request/response cycle.

    It provides a start_response function that adds some headers, and captures
    the start_response arguments. It can then wrap a WSGI response iterator in
    order to count the content-length and log the response.
    """

    def __init__(self,
                 environ,
                 start_response,
                 added_headers=None,
                 soft_timeout=-1):
        self.environ = environ
        self.original_start_response = start_response
        self.added_headers = added_headers
        self.soft_timeout = soft_timeout

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

        if 'SENTRY_ID' in self.environ:
            set_wsgi_header(
                headers,
                'X-Sentry-ID',
                self.environ['SENTRY_ID'],
            )

        self.status = status
        status_code, _, _ = status.partition(' ')
        self.status_code = int(status_code)
        self.headers = headers
        self.exc_info = exc_info

    def ensure_start_response(self, force=False):
        if force or not self.start_response_called:
            self.original_start_response(
                self.status,
                self.headers,
                self.exc_info,
            )
            self.start_response_called = True

    def wrap(self, response_iter):
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
            self.ensure_start_response()

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
            raise Exception("WSGIResponse: iterator has not been set yet")
        # We don't actually call the provided start_response until we start
        # iterating the content. This provides us with more control over the
        # response, and allows us to more cleanly switch to an error response
        # regardless of WSGI server implementation. Talisker apps can call
        # start_response multiple times, and only the final call will influence
        # the response status and headers. In Gunicorn for example, the headers
        # from all calls to start_response would be sent, which usually not
        # correct, and leads to duplictation or conflict of headers
        try:
            chunk = next(self.iter)
            # some WSGI apps don't actually call start_response() until they've
            # started iteration, so we delay calling the WSGI server's start
            # response until the last possible moment
            self.ensure_start_response()
        except (StopIteration, GeneratorExit):
            # not all middleware calls close, so ensure it's called.
            # Note: this does slightly affect the measured response latency,
            # which will not include time spent closing the client socket
            self.close()
            raise
        except Exception:
            self.report_error()
            # switch to generating an error response
            self.iter = iter(self.error(sys.exc_info()))
            chunk = next(self.iter)
        except KeyboardInterrupt:
            self.report_error()
            raise
        except SystemExit as e:
            if e.code != 0:
                self.report_error()
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

        self.ensure_start_response(force=True)
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

    def finish_request(self):
        start = self.environ.get('start_time')
        duration = 0
        response_latency = 0
        if start:
            duration = time.time() - start
            response_latency = (self.start_response_timestamp - start) * 1000

        log_response(
            self.environ,
            self.status_code,
            self.headers,
            duration,
            self.content_length,
            exc_info=self.exc_info,
            filepath=self.file_path,
        )

        if self.soft_timeout > 0 and response_latency > self.soft_timeout:
            try:
                talisker.sentry.report_wsgi_error(
                    self.environ,
                    msg='Start_response over timeout: {}ms'
                        .format(self.soft_timeout),
                    level='warning')
            except Exception:
                logger.exception('failed to send soft timeout report')

        talisker.clear_contexts()
        rid = self.environ.get('REQUEST_ID')
        if rid:
            REQUESTS.pop(rid, None)

    def report_error(self):
        sentry_id = talisker.sentry.report_wsgi_error(self.environ)
        if sentry_id is not None:
            self.environ['SENTRY_ID'] = sentry_id


class TaliskerMiddleware():
    """Talisker entrypoint for WSGI apps.

    Sets up some values in environ, handles errors, and wraps responses in
    WSGIResponse.
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

    def __call__(self, environ, start_response):
        start_time = time.time()
        config = talisker.get_config()
        environ['start_time'] = start_time
        if self.environ:
            environ.update(self.environ)

        # ensure request id
        if config.wsgi_id_header not in environ:
            environ[config.wsgi_id_header] = talisker.request_id.generate()
        rid = environ[config.wsgi_id_header]
        environ['REQUEST_ID'] = rid
        talisker.request_id.push(rid)

        REQUESTS[rid] = environ

        response = WSGIResponse(
            environ,
            start_response,
            self.headers,
            config.soft_request_timeout,
        )

        try:
            response_iter = self.app(environ, response.start_response)
        except Exception:
            response.report_error()
            response_iter = response.error(sys.exc_info())
        except KeyboardInterrupt:
            response.report_error()
            raise
        except SystemExit as e:
            if e.code != 0:
                response.report_error()
            raise

        return response.wrap(response_iter)


def get_metadata(environ,
                 status=None,
                 headers=None,
                 duration=None,
                 length=None,
                 exc_info=None,
                 filepath=None):
    """Return an ordered dictionary of request metadata for logging."""
    if headers is None:
        headers = {}
    else:
        headers = dict((k.lower(), v) for k, v in headers)
    extra = OrderedDict()
    extra['method'] = environ.get('REQUEST_METHOD')
    script = environ.get('SCRIPT_NAME', '')
    path = environ.get('PATH_INFO', '')
    extra['path'] = script + '/' + path.lstrip('/')
    qs = environ.get('QUERY_STRING')
    if qs:
        extra['qs'] = environ.get('QUERY_STRING')
    if status:
        extra['status'] = status
    if 'VIEW_NAME' in environ:
        extra['view'] = environ['VIEW_NAME']
    elif 'x-view-name' in headers:
        extra['view'] = headers['x-view-name']
    if duration:
        extra['duration_ms'] = round(duration * 1000, 3)
    extra['ip'] = environ.get('REMOTE_ADDR', None)
    extra['proto'] = environ.get('SERVER_PROTOCOL')
    if length:
        extra['length'] = length
    if filepath is not None:
        extra['filepath'] = filepath
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

    if exc_info and exc_info[0]:
        extra['exc_type'] = str(exc_info[0].__name__)
        extra['trailer'] = ''.join(
            traceback.format_exception(*exc_info)
        )

    tracking = getattr(talisker.context.CONTEXT, 'request_tracking', {})
    for name, tracker in tracking.items():
        extra[name + '_count'] = tracker.count
        extra[name + '_time_ms'] = tracker.time

    msg = "{method} {path}{0}".format('?' if 'qs' in extra else '', **extra)
    return msg, extra


def log_response(environ,
                 status=None,
                 headers=None,
                 duration=None,
                 length=None,
                 exc_info=None,
                 filepath=None,
                 timeout=False,
                 **kwargs):
    """Log a WSGI request and record metrics.

    Similar to access logs, but structured and with more data."""
    try:
        msg, extra = get_metadata(
            environ,
            status,
            headers,
            duration,
            length,
            exc_info,
            filepath,
        )
        if timeout:
            extra['timeout'] = True
        logger.info(msg, extra=extra)
    except Exception:
        logger.exception('error generating access log')
    else:
        labels = {
            'view': extra.get('view', 'unknown'),
            'method': extra['method'],
            'status': str(status).lower(),
        }

        WSGIMetric.requests.inc(**labels)
        WSGIMetric.latency.observe(extra['duration_ms'], **labels)
        if status is None and timeout:
            lbls = labels.copy()
            lbls.pop('status')
            WSGIMetric.timeouts.inc(**lbls)
        elif status >= 500:
            WSGIMetric.errors.inc(**labels)


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
