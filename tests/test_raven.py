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

import os

import talisker.raven
import talisker.logs
import talisker.revision

import raven.breadcrumbs
import raven.transport
import raven.base

from tests import conftest


def test_talisker_client_defaults(monkeypatch):
    monkeypatch.setitem(os.environ, 'TALISKER_ENV', 'production')
    monkeypatch.setitem(os.environ, 'TALISKER_UNIT', 'talisker-1')
    monkeypatch.setitem(os.environ, 'TALISKER_DOMAIN', 'example.com')

    client = conftest.sentry_client()

    # check client side
    assert client.processors == list(talisker.raven.default_processors)
    # this is unpleasant, but it saves us mocking
    assert raven.breadcrumbs.install_logging_hook.called is False
    assert raven.breadcrumbs._hook_requests.called is False
    assert raven.breadcrumbs._install_httplib.called is False

    # check message
    try:
        raise Exception('test')
    except:
        client.captureException()

    messages = conftest.sentry_messages(client)
    data = messages[0]

    assert data['release'] == talisker.revision.get()
    assert data['environment'] == 'production'
    assert data['server_name'] == 'talisker-1'
    assert data['tags']['site'] == 'example.com'




