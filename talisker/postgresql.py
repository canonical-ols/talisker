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

import collections
import logging
import math
import os
import sys
import time

import sqlparse
from psycopg2.extensions import cursor, connection
import raven.breadcrumbs

__all__ = [
    'TaliskerConnection',
    'TaliskerCursor',
    'prettify_sql',
]


def nocolor(sql):
    return sql


FILTERED = '<query filtered>'
color_sql = nocolor


if sys.stderr.isatty():
    try:
        from pygments import highlight
        from pygments.lexers.sql import PostgresLexer
        from pygments.formatters import TerminalTrueColorFormatter
    except ImportError:
        pass
    else:
        _lexer = PostgresLexer()
        _formatter = TerminalTrueColorFormatter()

        def docolor(sql):
            return highlight(sql, _lexer, _formatter).strip()

        color_sql = docolor


def prettify_sql(sql):
    if sql is None:
        return None
    return sqlparse.format(
        sql,
        keyword_case="upper",
        identfier_case="lower",
        strip_comments=False,
        reindent=True,
        indent_tabs=False)


class TaliskerConnection(connection):
    # FIXME: do this properly
    _mintime = int(os.environ.get('TALISKER_SLOWQUERY_TIME', '0'))
    _logger = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = logging.getLogger('talisker.slowqueries')
        return self._logger

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', TaliskerCursor)
        return super().cursor(*args, **kwargs)

    def _get_data(self, query, t):
        if callable(query):
            query = query()
        query = prettify_sql(query)
        query = FILTERED if query is None else query
        duration = '{:d}ms'.format(int(math.ceil(t)))
        connection = '{user}@{host}:{port}/{dbname}'.format(
                **self.get_dsn_parameters())
        return query, duration, connection

    def _record(self, msg, query, duration):
        query_data = None

        if duration > self._mintime:
            query_data = self._get_data(query, duration)
            extra = collections.OrderedDict()
            extra['trailer'] = color_sql(query_data[0])
            extra['duration'] = query_data[1]
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
            self.connection._record('executed query', query, duration)

    def callproc(self, procname, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).callproc(procname, vars)
        finally:
            duration = (time.time() - timestamp) * 1000
            # no query parameters, cannot safely record
            if vars is None:
                query = None
            else:
                # lazy query sanitizing
                def query():
                    q = self.query
                    for var in vars:
                        v = self.mogrify('%s', [var])
                        q = q.replace(v, b'%s')
                    return q.decode('utf8')

            self.connection._record(
                'stored proc: {}'.format(procname), query, duration)
