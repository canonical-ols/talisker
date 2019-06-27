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

import pytest
from freezegun import freeze_time

try:
    import psycopg2  # NOQA
except ImportError:
    pytest.skip("skipping postgres only tests", allow_module_level=True)

# need for some fixtures
from tests import conftest  # noqa
from talisker.postgresql import (
    TaliskerConnection,
    prettify_sql,
    get_safe_connection_string,
    FILTERED,
)
import talisker.sentry


@pytest.fixture
def conn(postgresql):
    return TaliskerConnection(postgresql.dsn)


@pytest.fixture
def cursor(conn):
    return conn.cursor()


def test_connection_record_slow(conn, context, get_breadcrumbs):
    query = 'select * from table'
    conn._threshold = 0
    conn._record('msg', query, 10000)
    records = context.logs.filter(name='talisker.slowqueries')
    assert records[0].extra['duration_ms'] == 10000.0
    assert records[0]._trailer == prettify_sql(query)


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_connection_record_fast(conn, context):
    query = 'select * from table'
    conn._record('msg', query, 0)
    context.assert_not_log(name='talisker.slowqueries')


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_connection_record_breadcrumb(conn, get_breadcrumbs):
    query = 'select * from table'
    conn._record('msg', query, 1000)
    breadcrumb = get_breadcrumbs()[0]
    assert breadcrumb['message'] == 'msg'
    assert breadcrumb['category'] == 'sql'
    assert breadcrumb['data']['duration'] == 1000.0
    assert breadcrumb['data']['connection'] == \
        get_safe_connection_string(conn)
    assert 'query' in breadcrumb['data']


@freeze_time()
def test_cursor_sets_statement_timeout(cursor, get_breadcrumbs):
    talisker.Context.current.set_deadline(1000)
    cursor.execute('select %s', [1])
    crumbs = get_breadcrumbs()
    assert crumbs[0]['data']['query'] == 'SELECT %s'
    assert crumbs[0]['data']['timeout'] == 1000


def test_cursor_actually_times_out(cursor, get_breadcrumbs):
    talisker.Context.current.set_deadline(10)
    with pytest.raises(psycopg2.errors.QueryCanceled):
        cursor.execute('select pg_sleep(1)', [1])
    breadcrumb = get_breadcrumbs()[0]
    assert breadcrumb['data']['cancelled'] is True


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_cursor_execute_no_params(cursor, get_breadcrumbs):
    cursor.execute('select 1')
    breadcrumb = get_breadcrumbs()[0]
    assert breadcrumb['data']['query'] == FILTERED


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_cursor_callproc_with_params(cursor, get_breadcrumbs):
    cursor.execute(
        """CREATE OR REPLACE FUNCTION test(integer) RETURNS integer
               AS 'select $1'
               LANGUAGE SQL;""")
    cursor.callproc('test', [1])
    breadcrumb = get_breadcrumbs()[1]
    assert breadcrumb['data']['query'] == FILTERED


@pytest.mark.skipif(not talisker.sentry.enabled, reason='need raven installed')
def test_cursor_callproc_no_params(cursor, get_breadcrumbs):
    cursor.execute(
        """CREATE OR REPLACE FUNCTION test() RETURNS integer
               AS 'select 1'
               LANGUAGE SQL;""")
    cursor.callproc('test')
    breadcrumb = get_breadcrumbs()[0]
    assert breadcrumb['data']['query'] == FILTERED
