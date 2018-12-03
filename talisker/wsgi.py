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

from werkzeug.datastructures import Headers

import talisker.request_id
import talisker.context
import talisker.endpoints
import talisker.statsd
import talisker.requests
import talisker.sentry


__all__ = [
    'set_environ',
    'set_headers',
    'wrap'
]


def set_environ(app, **kwargs):
    def middleware(environ, start_response):
        for key, value in kwargs.items():
            environ[key] = value
        return app(environ, start_response)
    return middleware


def set_headers(app, add_headers):
    """Adds headers to response, overwriting any existing values."""
    def middleware(environ, start_response):
        def custom_start_response(status, response_headers, exc_info=None):
            headers = Headers(response_headers)
            for header, value in add_headers.items():
                headers.set(header, value)
            return start_response(status, headers, exc_info)
        return app(environ, custom_start_response)
    return middleware


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
