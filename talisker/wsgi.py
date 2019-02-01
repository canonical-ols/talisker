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

import talisker.request_id
from talisker.context import CONTEXT
import talisker.endpoints
import talisker.statsd
import talisker.requests
import talisker.sentry
from talisker.util import set_wsgi_header


__all__ = [
    'set_environ',
    'set_headers',
    'wrap'
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


def get_metadata(environ,
                 status,
                 headers,
                 duration=None,
                 length=None):
    headers = dict((k.lower(), v) for k, v in headers)
    extra = OrderedDict()
    extra['method'] = environ.get('REQUEST_METHOD')
    extra['path'] = environ.get('PATH_INFO')
    qs = environ.get('QUERY_STRING')
    if qs is not None:
        extra['qs'] = environ.get('QUERY_STRING')
    extra['status'] = status
    if 'x-view-name' in headers:
        extra['view'] = headers['x-view-name']
    extra['duration_ms'] = round(duration * 1000, 3)
    extra['ip'] = environ.get('REMOTE_ADDR', None)
    extra['proto'] = environ.get('SERVER_PROTOCOL')
    extra['length'] = length
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
    extra['ua'] = environ.get('HTTP_USER_AGENT', None)

    tracking = getattr(talisker.context.CONTEXT, 'request_tracking', {})
    for name, tracker in tracking.items():
        extra[name + '_count'] = tracker.count
        extra[name + '_time_ms'] = tracker.time

    msg = "{method} {path}{0}".format('?' if extra['qs'] else '', **extra)
    return msg, extra


def wrap(app):
    if getattr(app, '_talisker_wrapped', False):
        return app

    config = talisker.config.get_config()

    wrapped = app
    # added in reverse order
    wrapped = set_headers(
        wrapped, {'X-VCS-Revision': config.revision_id})
    # expose some standard endpoint
    wrapped = talisker.endpoints.StandardEndpointMiddleware(wrapped)
    # set some standard environ items
    wrapped = set_environ(
        wrapped,
        statsd=talisker.statsd.get_client(),
        requests=talisker.requests.get_session(),
    )
    # add request id info to thread locals
    wrapped = talisker.request_id.RequestIdMiddleware(wrapped)
    wrapped = talisker.sentry.TaliskerSentryMiddleware(wrapped)
    wrapped._talisker_wrapped = True
    wrapped._talisker_original_app = app
    return wrapped
