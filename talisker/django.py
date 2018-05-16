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
        super().capture(event_type, tags=tags, extra=extra, **kwargs)


def middleware(get_response):
    """Set up middleware to add X-View-Name header."""
    def add_view_name(request):
        response = get_response(request)
        if getattr(request, 'resolver_match', None):
            response['X-View-Name'] = request.resolver_match.view_name
        return response
    return add_view_name
