#
# Copyright (c) 2015-2018 Canonical, Ltd.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
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
        from_env = talisker.sentry.ensure_talisker_config(kwargs)
        logging.getLogger(__name__).info(
            'updating raven config from django app')
        super().__init__(*args, **kwargs)
        talisker.sentry.log_client(self, from_env)
        talisker.sentry.set_client(self)

    def capture(self, event_type, tags=None, extra=None, **kwargs):
        tags, extra = talisker.sentry.add_talisker_context(tags, extra)
        return super().capture(event_type, tags=tags, extra=extra, **kwargs)


def middleware(get_response):
    """Set up middleware to add X-View-Name header."""
    def add_view_name(request):
        response = get_response(request)
        if getattr(request, 'resolver_match', None):
            response['X-View-Name'] = request.resolver_match.view_name
        return response
    return add_view_name
