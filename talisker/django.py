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

from raven.contrib.django.client import DjangoClient

from talisker.sentry import ensure_talisker_config, log_client, update_clients


# raven's django support does some very odd things.
# There is a module global, that is a proxy to the output of
# raven.contrib.django.models.get_client()
# But the only way thing you can customise about the client is it's base class.
# So that's what we do. We ensure talisker's configuration, and hook it in to
# the other things that need to know about the client.
# Django users just need to add the following to settings:
# SENTRY_CLIENT = 'talisker.django.SentryClient

class SentryClient(DjangoClient):
    def __init__(self, **kwargs):
        from_env = ensure_talisker_config(kwargs)
        super().__init__(**kwargs)
        log_client(self, from_env)
        update_clients(self)
