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

import pytest

import raven.context
from tests import conftest  # noqa
from talisker.postgresql import (
    TaliskerConnection,
    prettify_sql,
    get_safe_connection_string,
    FILTERED,
)


@pytest.fixture
def conn(postgresql):
    return TaliskerConnection(postgresql.dsn)


@pytest.fixture
def cursor(conn):
    return conn.cursor()


@pytest.fixture
def breadcrumbs():
    with raven.context.Context() as ctx:
        yield ctx.breadcrumbs


def test_connection_record_slow(conn, log, breadcrumbs):
    query = 'select * from table'
    conn._threshold = 0
    conn._record('msg', query, 10000)
    record = log[0]
    assert record._structured['duration_ms'] == 10000.0
    assert record._trailer == prettify_sql(query)


def test_connection_record_fast(conn, log):
    query = 'select * from table'
    conn._record('msg', query, 0)
    assert not log


def test_connection_record_breadcrumb(conn, breadcrumbs):
    query = 'select * from table'
    conn._record('msg', query, 1000)
    breadcrumb = breadcrumbs.get_buffer()[0]
    assert breadcrumb['message'] == 'msg'
    assert breadcrumb['category'] == 'sql'
    assert breadcrumb['data']['duration'] == 1000.0
    assert breadcrumb['data']['connection'] == \
        get_safe_connection_string(conn)
    assert 'query' in breadcrumb['data']


def test_cursor_execute_with_params(cursor, breadcrumbs):
    cursor.execute('select %s', [1])
    breadcrumb = breadcrumbs.get_buffer()[0]
    assert breadcrumb['data']['query'] == prettify_sql('select %s')


def test_cursor_execute_no_params(cursor, breadcrumbs):
    cursor.execute('select 1')
    breadcrumb = breadcrumbs.get_buffer()[0]
    assert breadcrumb['data']['query'] == FILTERED


def test_cursor_callproc_with_params(cursor, breadcrumbs):
    cursor.execute(
        """CREATE OR REPLACE FUNCTION test(integer) RETURNS integer
               AS 'select $1'
               LANGUAGE SQL;""")
    cursor.callproc('test', [1])
    breadcrumb = breadcrumbs.get_buffer()[1]
    assert breadcrumb['data']['query'] == FILTERED


def test_cursor_callproc_no_params(cursor, breadcrumbs):
    cursor.execute(
        """CREATE OR REPLACE FUNCTION test() RETURNS integer
               AS 'select 1'
               LANGUAGE SQL;""")
    cursor.callproc('test')
    breadcrumb = breadcrumbs.get_buffer()[0]
    assert breadcrumb['data']['query'] == FILTERED
