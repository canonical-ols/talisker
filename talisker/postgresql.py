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

import collections
import logging
import time
import shlex

from psycopg2.extensions import cursor, connection

try:
    from sqlparse import format as format_sql
except ImportError:
    def format_sql(sql, *args, **kwargs):
        return sql

import raven.breadcrumbs
import talisker

__all__ = [
    'TaliskerConnection',
    'TaliskerCursor',
    'prettify_sql',
]


FILTERED = '<query filtered>'


def prettify_sql(sql):
    if sql is None:
        return None
    return format_sql(
        sql,
        keyword_case="upper",
        identfier_case="lower",
        strip_comments=False,
        reindent=True,
        indent_tabs=False)


def get_safe_connection_string(conn):
    try:
        try:
            # 2.7+
            params = conn.get_dsn_parameters()
        except AttributeError:
            params = dict(i.split('=') for i in shlex.split(conn.dsn))

        params.setdefault('host', 'localhost')
        return '{user}@{host}:{port}/{dbname}'.format(**params)
    except Exception:
        return 'could not parse dsn'


class TaliskerConnection(connection):
    _logger = None
    _threshold = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = logging.getLogger('talisker.slowqueries')
        return self._logger

    @property
    def query_threshold(self):
        if self._threshold is None:
            self._threshold = talisker.get_config()['slowquery_threshold']
        return self._threshold

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', TaliskerCursor)
        return super().cursor(*args, **kwargs)

    def _get_data(self, query, t):
        if callable(query):
            query = query()
        query = prettify_sql(query)
        query = FILTERED if query is None else query
        duration = float(round(t, 3))
        connection = get_safe_connection_string(self)
        return query, duration, connection

    def _record(self, msg, query, duration):
        query_data = None

        if self.query_threshold >= 0 and duration > self.query_threshold:
            query_data = self._get_data(query, duration)
            extra = collections.OrderedDict()
            extra['trailer'] = query_data[0]
            extra['duration_ms'] = query_data[1]
            extra['connection'] = query_data[2]
            self.logger.info('slow ' + msg, extra=extra)

        def processor(data):
            if query_data is None:
                q, ms, conn = self._get_data(query, duration)
            else:
                q, ms, conn = query_data
            data['data']['query'] = q
            data['data']['duration'] = ms
            data['data']['connection'] = conn

        breadcrumb = dict(
            message=msg, category='sql', data={}, processor=processor)

        raven.breadcrumbs.record(**breadcrumb)


class TaliskerCursor(cursor):

    def execute(self, query, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).execute(query, vars)
        finally:
            duration = (time.time() - timestamp) * 1000
            if vars is None:
                query = None
            self.connection._record('query', query, duration)

    def callproc(self, procname, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).callproc(procname, vars)
        finally:
            duration = (time.time() - timestamp) * 1000
            # no query parameters, cannot safely record
            self.connection._record(
                'stored proc: {}'.format(procname), None, duration)
