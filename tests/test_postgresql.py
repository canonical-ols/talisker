##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

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
