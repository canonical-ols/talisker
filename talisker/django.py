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
import logging
from raven.contrib.django.client import DjangoClient

import talisker.sentry


# raven's django support does some very odd things.
# There is a module global, that is a proxy to the output of
# raven.contrib.django.models.get_client()
# But the only way you can customise the set up is via subclassing the client.
# So that's what we do. We ensure talisker's configuration, and hook it in to
# the other things that need to know about the client.  Django users just need
# to add the following to settings:
# SENTRY_CLIENT = 'talisker.django.SentryClient'

class SentryClient(DjangoClient):
    def __init__(self, *args, **kwargs):
        # SQL hook sends raw SQL to the server. Not cool, bro.
        kwargs['install_sql_hook'] = False
        talisker.sentry.ensure_talisker_config(kwargs)
        logging.getLogger(__name__).info(
            'updating raven config from django app')
        super().__init__(*args, **kwargs)
        # update any previously configured sentry client
        talisker.sentry.set_client(self)

    def build_msg(self, event_type, *args, **kwargs):
        data = super().build_msg(event_type, *args, **kwargs)
        talisker.sentry.add_talisker_context(data)
        return data

    def set_dsn(self, dsn=None, transport=None):
        super().set_dsn(dsn, transport)
        talisker.sentry.log_client(self)


def middleware(get_response):
    """Set up middleware to add X-View-Name header."""
    def add_view_name(request):
        response = get_response(request)
        if getattr(request, 'resolver_match', None):
            response['X-View-Name'] = request.resolver_match.view_name
        return response
    return add_view_name
