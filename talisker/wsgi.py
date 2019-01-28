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
import talisker.sentry
import talisker.statsd
from talisker.util import set_wsgi_header


logger = logging.getLogger('talisker.wsgi')

__all__ = [
    'HEADER',
    'wrap',
]


class WSGIMetric:
    latency = talisker.metrics.Histogram(
        name='wsgi_latency',
        documentation='Duration of requests served by WSGI',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
        buckets=[4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192],
    )

    count = talisker.metrics.Counter(
        name='wsgi_count',
        documentation='Count of gunicorn requests',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )

    errors = talisker.metrics.Counter(
        name='wsgi_errors',
        documentation='Count of WSGI errors',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )


class WSGIResponse(object):
    """Container for WSGI request/response cycle.

    It adds some headers to the response, and captures the status, headers and
    content length for obervability.
    """

    def __init__(self, environ, start_response, added_headers=None):
        self.environ = environ
        self.original_start_response = start_response
        self.added_headers = added_headers

        # response metadata
        self.status = None
        self.headers = None
        self.exc_info = None
        self.iter = None
        self.status_code = 0
        self.content_length = 0
        self.file_path = None
        self.closed = False
        self.start_response_called = False

    def start_response(self, status, headers, exc_info=None):
        """Adds response headers and stores response data.

        Does not directly call upstream start_response - that is done upon
        iteration, to provide more control over status/headers in the case of
        an error.
        """
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

        self.status = status
        status_code, _, _ = status.partition(' ')
        self.status_code = int(status_code)
        self.headers = headers
        self.exc_info = exc_info

    def ensure_start_response(self):
        if not self.start_response_called:
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
                self.log()
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
        self.ensure_start_response()
        try:
            chunk = next(self.iter)
        except (StopIteration, GeneratorExit):
            # not all middleware calls close, so ensure it's called.
            # Note: this does slightly affect the measured response latency,
            # which will not include time spent closing the client socket
            self.close()
            raise
        except Exception:
            # switch to generating an error response
            self.iter = iter(self.error(sys.exc_info()))
            chunk = next(self.iter)

        self.content_length += len(chunk)
        return chunk

    def error(self, exc_info):
        """Generate a WSGI response describing the error."""
        # TODO: make this better, including json errors
        self.start_response(
            '500 Internal Server Error',
            [('Content-Type', 'text/plain')],
            exc_info,
        )
        # Note: the original start_response should raise if headers have been
        # sent, which should bubble up to the WSGI server.
        self.original_start_response(
            self.status,
            self.headers,
            self.exc_info,
        )

        if talisker.get_config().devel:
            lines = traceback.format_exception(*exc_info)
            return [''.join(lines).encode('utf8')]
        else:
            return [exc_info[0].__name__.encode('utf8')]

    def close(self):
        """Close and record the response."""
        if self.closed:
            return

        try:
            iter_close = getattr(self.iter, 'close', None)
            if iter_close:
                iter_close()
        finally:
            self.log()
            self.closed = True

    def log(self):
        duration = time.time() - self.environ['start_time']
        log_response(
            self.environ,
            self.status_code,
            self.headers,
            duration,
            self.content_length,
            exc_info=self.exc_info,
            filepath=self.file_path,
        )


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
        environ['start_time'] = start_time
        config = talisker.get_config()

        # ensure request id
        if config.wsgi_id_header not in environ:
            environ[config.wsgi_id_header] = talisker.request_id.generate()
        rid = environ[config.wsgi_id_header]
        talisker.request_id.push(rid)

        # setup environment
        environ['REQUEST_ID'] = rid
        if self.environ:
            for key, value in self.environ.items():
                environ[key] = value

        response = WSGIResponse(environ, start_response, self.headers)

        try:
            response_iter = self.app(environ, response.start_response)
        except Exception:
            response_iter = response.error(sys.exc_info())

        return response.wrap(response_iter)


def get_metadata(environ,
                 status,
                 headers,
                 duration,
                 length,
                 exc_info=None,
                 trailer=True,
                 filepath=None):
    """Return an ordered dictionary of request metadata for logging."""
    headers = dict((k.lower(), v) for k, v in headers)
    extra = OrderedDict()
    extra['method'] = environ.get('REQUEST_METHOD')
    extra['path'] = environ.get('PATH_INFO')
    qs = environ.get('QUERY_STRING')
    if qs:
        extra['qs'] = environ.get('QUERY_STRING')
    extra['status'] = status
    if 'x-view-name' in headers:
        extra['view'] = headers['x-view-name']
    extra['duration_ms'] = round(duration * 1000, 3)
    extra['ip'] = environ.get('REMOTE_ADDR', None)
    extra['proto'] = environ.get('SERVER_PROTOCOL')
    extra['length'] = length
    if filepath is not None:
        extra['filepath'] = filepath
    if 'CONTENT_LENGTH' in environ:
        try:
            extra['request_length'] = int(environ['CONTENT_LENGTH'])
        except ValueError:
            pass
    if 'CONTENT_TYPE' in environ:
        extra['request_type'] = environ['CONTENT_TYPE']
    referrer = environ.get('HTTP_REFERER', None)
    if referrer is not None:
        extra['referrer'] = environ.get('HTTP_REFERER', None)
    if 'HTTP_X_FORWARDED_FOR' in environ:
        extra['forwarded'] = environ['HTTP_X_FORWARDED_FOR']
    if 'HTTP_USER_AGENT' in environ:
        extra['ua'] = environ['HTTP_USER_AGENT']

    if exc_info and exc_info[0]:
        extra['exc_type'] = str(exc_info[0].__name__)
        if trailer:
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
                 status,
                 headers,
                 duration,
                 length,
                 exc_info=None,
                 trailer=True,
                 filepath=None):
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
            trailer,
            filepath,
        )
        logger.info(msg, extra=extra)
    except Exception:
        logger.exception('error generating access log')
    else:
        labels = {
            'view': extra.get('view', 'unknown'),
            'method': extra['method'],
            'status': str(status),
        }

        WSGIMetric.count.inc(**labels)
        WSGIMetric.latency.observe(extra['duration_ms'], **labels)
        if status >= 500:
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
    wrapped = talisker.sentry.TaliskerSentryMiddleware(wrapped)
    wrapped = TaliskerMiddleware(wrapped, environ, headers)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
