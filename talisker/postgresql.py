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
import math
import os
import sqlparse
import time

from psycopg2.extensions import cursor, connection
import raven.breadcrumbs

__all__ = [
    'run',
]


def sanitize(query, vars):
    if not query:
        return None
    if not vars:
        return query
    sql = query
    if vars:
        for var in vars:
            if isinstance(var, str):
                sql = sql.replace(var, '*' * len(var))
    return sql


def prettify_sql(sql):
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

    def _record(self, msg, query, vars, cursor, timestamp):
        t = (time.time() - timestamp) * 1000

        query_data = {
            'duration': '{:d}ms'.format(math.ceil(t)),
            'connection': '{user}@{host}:{port}/{dbname}'.format(
                **self.get_dsn_parameters()),
        }

        if t > self._mintime:
            query_data['query'] = sanitize(query, vars)
            self.logger.info('slow ' + msg, extra=query_data)

        def processor(data):
            if 'query' not in data['data']:
                data['data']['query'] = sanitize(query, vars)
            data['data']['query'] = prettify_sql(data['data']['query'])

        breadcrumb = dict(
            message=msg, category='sql', data=query_data, processor=processor)

        raven.breadcrumbs.record(**breadcrumb)

    def _record_execute(self, query, vars, cursor, timestamp):
        self._record('executed query', query, vars, cursor, timestamp)

    def _record_proc(self, procname, vars, cursor, timestamp):
        self._record(
            'stored proc: {}'.format(procname),
            None,
            vars,
            cursor,
            timestamp)


class TaliskerCursor(cursor):

    def execute(self, query, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).execute(query, vars)
        finally:
            self.connection._record_execute(query, vars, self, timestamp)

    def callproc(self, procname, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).callproc(procname, vars)
        finally:
            self.connection._record_proc(procname, vars, self, timestamp)
