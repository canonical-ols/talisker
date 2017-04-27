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

import talisker.sentry
import talisker.logs
import talisker.revision

import raven.breadcrumbs
import raven.transport
import raven.base
import raven.handlers.logging
import raven.middleware

from tests import conftest


def test_talisker_client_defaults(monkeypatch, log):
    monkeypatch.setitem(os.environ, 'TALISKER_ENV', 'production')
    monkeypatch.setitem(os.environ, 'TALISKER_UNIT', 'talisker-1')
    monkeypatch.setitem(os.environ, 'TALISKER_DOMAIN', 'example.com')

    client = talisker.sentry.get_client.uncached(
        dsn=conftest.DSN, transport=conftest.DummyTransport)

    assert 'configured raven' in log[-1].msg

    # check client side
    assert (list(sorted(client.processors)) ==
            list(sorted(talisker.sentry.default_processors)))
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


def test_talisker_client_defaults_none(monkeypatch, log):
    monkeypatch.setitem(os.environ, 'TALISKER_ENV', 'production')
    monkeypatch.setitem(os.environ, 'TALISKER_UNIT', 'talisker-1')
    monkeypatch.setitem(os.environ, 'TALISKER_DOMAIN', 'example.com')

    # raven flask integration passes in all possible kwargs as None
    kwargs = {
        'release': None,
        'hook_libraries': None,
        'site': None,
        'environment': None,
        'name': None,
    }
    client = talisker.sentry.get_client.uncached(
        dsn=conftest.DSN, transport=conftest.DummyTransport, **kwargs)

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


def test_talisker_client_defaults_explicit_config(monkeypatch, log):
    monkeypatch.setitem(os.environ, 'TALISKER_ENV', 'production')
    monkeypatch.setitem(os.environ, 'TALISKER_UNIT', 'talisker-1')
    monkeypatch.setitem(os.environ, 'TALISKER_DOMAIN', 'example.com')

    # raven flask integration passes in all possible kwargs as None
    kwargs = {
        'release': 'release',
        'hook_libraries': ['requests'],
        'site': 'site',
        'environment': 'environment',
        'name': 'name',
    }
    client = talisker.sentry.get_client.uncached(
        dsn=conftest.DSN, transport=conftest.DummyTransport, **kwargs)

    # this is unpleasant, but it saves us mocking
    assert raven.breadcrumbs.install_logging_hook.called is False
    assert raven.breadcrumbs._hook_requests.called is True
    assert raven.breadcrumbs._install_httplib.called is False

    # check message
    try:
        raise Exception('test')
    except:
        client.captureException()

    messages = conftest.sentry_messages(client)
    data = messages[0]

    assert data['release'] == 'release'
    assert data['environment'] == 'environment'
    assert data['server_name'] == 'name'
    assert data['tags']['site'] == 'site'


def test_log_client(monkeypatch, log):
    dsn = 'http://user:pass@host:8000/app'
    client = raven.Client(dsn)
    talisker.sentry.log_client(client, False)
    assert 'pass' not in log[-1]._structured['host']
    assert 'from SENTRY_DSN' not in log[-1].msg
    talisker.sentry.log_client(client, True)
    assert 'pass' not in log[-1]._structured['host']
    assert 'from SENTRY_DSN' in log[-1].msg


def test_get_middlware():
    mw = talisker.sentry.get_middleware(lambda: None)
    assert isinstance(mw, raven.middleware.Sentry)
    assert mw.client == talisker.sentry.get_client()
    updates = talisker.sentry.sentry_globals['updates']
    assert len(updates) == 1
    assert updates[0].__closure__[0].cell_contents == mw


def test_get_log_handler():
    lh = talisker.sentry.get_log_handler()
    assert isinstance(lh, raven.handlers.logging.SentryHandler)
    assert lh.client == talisker.sentry.get_client()
    updates = talisker.sentry.sentry_globals['updates']
    assert len(updates) == 1
    assert updates[0].__closure__[0].cell_contents == lh


def test_update_client():
    client = talisker.sentry.get_client()
    lh = talisker.sentry.get_log_handler()
    mw = talisker.sentry.get_middleware(lambda: None)
    assert lh.client is client
    assert mw.client is client
    new_client = talisker.sentry.configure_client()
    assert talisker.sentry.get_client() is new_client
    assert lh.client is new_client
    assert mw.client is new_client
