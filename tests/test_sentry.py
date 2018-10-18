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

import os
import logging
import time

import talisker.sentry
import talisker.logs
import talisker.request_id
import talisker.revision

import raven.breadcrumbs
import raven.transport
import raven.base
import raven.handlers.logging
import raven.middleware
from freezegun import freeze_time

from talisker.testing import setup_test_sentry_client, run_wsgi

DATESTRING = '2016-01-02 03:04:05.1234'


@freeze_time(DATESTRING)
def test_talisker_client_defaults(monkeypatch, context):
    monkeypatch.setitem(os.environ, 'TALISKER_ENV', 'production')
    monkeypatch.setitem(os.environ, 'TALISKER_UNIT', 'talisker-1')
    monkeypatch.setitem(os.environ, 'TALISKER_DOMAIN', 'example.com')

    client, messages = setup_test_sentry_client()

    assert context.logs.exists(msg='configured raven')

    # check client side
    assert (list(sorted(client.processors)) ==
            list(sorted(talisker.sentry.default_processors)))
    # this is unpleasant, but it saves us mocking
    assert raven.breadcrumbs.install_logging_hook.called is False
    assert raven.breadcrumbs._hook_requests.called is False
    assert raven.breadcrumbs._install_httplib.called is False

    # check message
    try:
        client.extra_context({'start_time': time.time() - 1})
        raven.breadcrumbs.record(msg='foo')
        raise Exception('test')
    except Exception:
        client.captureException()

    data = messages[0]

    assert data['release'] == talisker.revision.get()
    assert data['tags'] == {
        'environment': 'production',
        'unit': 'talisker-1',
        'domain': 'example.com',
    }
    assert all(
        c['data']['start'] == 1000 for c in data['breadcrumbs']['values']
    )


def test_talisker_client_defaults_none(monkeypatch):
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
    client, messages = setup_test_sentry_client(**kwargs)

    # this is unpleasant, but it saves us mocking
    assert raven.breadcrumbs.install_logging_hook.called is False
    assert raven.breadcrumbs._hook_requests.called is False
    assert raven.breadcrumbs._install_httplib.called is False

    # check message
    try:
        raise Exception('test')
    except Exception:
        client.captureException()

    data = messages[0]

    assert data['release'] == talisker.revision.get()
    assert data['tags'] == {
        'environment': 'production',
        'unit': 'talisker-1',
        'domain': 'example.com',
    }


def test_talisker_client_defaults_explicit_config(monkeypatch):
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
    client, messages = setup_test_sentry_client(**kwargs)

    # this is unpleasant, but it saves us mocking
    assert raven.breadcrumbs.install_logging_hook.called is False
    assert raven.breadcrumbs._hook_requests.called is True
    assert raven.breadcrumbs._install_httplib.called is False

    # check message
    try:
        raise Exception('test')
    except Exception:
        client.captureException()

    data = messages[0]

    assert data['release'] == 'release'
    assert data['environment'] == 'environment'
    assert data['server_name'] == 'name'
    assert data['tags']['site'] == 'site'


def test_log_client(monkeypatch, context):
    dsn = 'http://user:pass@host:8000/app'
    client = talisker.sentry.TaliskerSentryClient(dsn=dsn)
    talisker.sentry.log_client(client, False)

    assert 'pass' not in context.logs[-1].extra['dsn']
    assert 'from SENTRY_DSN' not in context.logs[-1].msg
    talisker.sentry.log_client(client, True)
    assert 'pass' not in context.logs[-1].extra['dsn']
    assert 'from SENTRY_DSN' in context.logs[-1].msg


def test_get_middlware():
    mw = talisker.sentry.get_middleware(lambda: None)
    assert isinstance(mw, talisker.sentry.TaliskerSentryMiddleware)
    assert mw.client == talisker.sentry.get_client()
    updates = talisker.sentry.sentry_globals['updates']
    assert len(updates) == 1
    assert updates[0].__closure__[0].cell_contents == mw


def test_add_talisker_context():
    data = {
        'tags': {'foo': 'bar'},
        'extra': {
            'foo': 'bar',
            'start_time': 10,
        },
        'breadcrumbs': {
            'values': [
                {'timestamp': 10.2, 'category': 'default', 'data': {}},
                {'timestamp': 10.5, 'category': 'default', 'data': {}},
            ],
        },
    }

    with talisker.request_id.context('id'):
        with talisker.logs.logging_context({'test': 'test'}):
            talisker.sentry.add_talisker_context(data)

    assert data['tags'] == {
        'foo': 'bar',
        'request_id': 'id',
    }
    assert data['extra'] == {
        'foo': 'bar',
        'test': 'test',
        'start_time': 10,
        'request_id': 'id',
    }
    assert data['breadcrumbs']['values'] == [
        {'timestamp': 10.2, 'category': 'default', 'data': {'start': 200.0}},
        {'timestamp': 10.5, 'category': 'default', 'data': {'start': 500.0}},
    ]


@freeze_time(DATESTRING)
def test_sql_summary_crumb():
    crumbs = [
        {'category': 'sql', 'data': {'duration': 10.0, 'query': '1'}},
        {'category': 'sql', 'data': {'duration': 15.0, 'query': '2'}},
        {'category': 'sql', 'data': {'duration': 13.0, 'query': '3'}},
        {'category': 'sql', 'data': {'duration': 5.0, 'query': '4'}},
        {'category': 'sql', 'data': {'duration': 11.0, 'query': '5'}},
        {'category': 'sql', 'data': {'duration': 7.0, 'query': '6'}},
        {'category': 'sql', 'data': {'duration': 4.0, 'query': '7'}},
    ]

    start_time = time.time() - 0.5  # 500ms
    summary = talisker.sentry.sql_summary(crumbs, start_time)
    assert summary == {
        'sql_count': 7,
        'sql_time': 65.0,
        'total_time': 500.0,
        'non_sql_time': 435.0,
        'slowest queries': [
            {'duration': 15.0, 'query': '2'},
            {'duration': 13.0, 'query': '3'},
            {'duration': 11.0, 'query': '5'},
            {'duration': 10.0, 'query': '1'},
            {'duration': 7.0, 'query': '6'},
        ],
    }


def test_middleware_soft_request_timeout(monkeypatch, environ, context):
    monkeypatch.setitem(os.environ, 'TALISKER_SOFT_REQUEST_TIMEOUT', '0')

    def app(environ, start_response):
        start_response(200, [])
        return []

    mw = talisker.sentry.get_middleware(app)
    body, _, _ = run_wsgi(mw, environ)
    list(body)
    assert 'Start_response over timeout: 0' == context.sentry[0]['message']
    assert 'warning' == context.sentry[0]['level']


def test_middleware_soft_request_timeout_non_zero(
        monkeypatch, environ, context):
    monkeypatch.setitem(os.environ, 'TALISKER_SOFT_REQUEST_TIMEOUT', '100')

    def app(environ, start_response):
        time.sleep(200 / 1000.0)
        start_response(200, [])
        return []

    mw = talisker.sentry.get_middleware(app)
    body, _, _ = run_wsgi(mw, environ)
    list(body)
    assert 'Start_response over timeout: 100' == context.sentry[0]['message']


def test_middleware_soft_request_timeout_disabled_by_default(
        environ, context):
    def app(environ, start_response):
        start_response(200, [])
        return []

    mw = talisker.sentry.get_middleware(app)
    body, _, _ = run_wsgi(mw, environ)
    list(body)
    assert len(context.sentry) == 0


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


def test_logs_ignored():
    client, messages = setup_test_sentry_client()

    client.context.clear()
    # set up a root logger with a formatter
    logging.getLogger('talisker.slowqueries').info('talisker.slowqueries')
    logging.getLogger('talisker.requests').info('talisker.requests')
    logging.getLogger('talisker').info('talisker')
    try:
        raise Exception('test')
    except Exception:
        client.captureException()

    data = messages[0]
    assert len(data['breadcrumbs']) == 1
    crumb = data['breadcrumbs']['values'][0]
    assert crumb['message'] == 'talisker'
    assert crumb['category'] == 'talisker'
