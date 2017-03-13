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
import sqlparse
import time

from psycopg2.extensions import cursor, connection
import raven.breadcrumbs

__all__ = [
    'TaliskerConnection',
    'TaliskerCursor',
    'prettify_sql',
]

FILTERED = '<filtered>'


def prettify_sql(sql):
    if sql == FILTERED:
        return sql
    return sqlparse.format(
        sql,
        keyword_case="upper",
        identfier_case="lower",
        strip_comments=False,
        reindent=True,
        indent_tabs=False)


class TaliskerConnection(connection):
    # FIXME: do this properly
    _mintime = int(os.environ.get('TALISKER_SLOWQUERY_TIME', '5000'))
    _logger = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = logging.getLogger('talisker.slowqueries')
        return self._logger

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', TaliskerCursor)
        return super().cursor(*args, **kwargs)

    def _add_extra(self, extra, query, t):
        extra['duration'] = '{:d}ms'.format(int(math.ceil(t)))
        if callable(query):
            query = query()
        extra['query'] = FILTERED if query is None else query
        extra['connection'] = '{user}@{host}:{port}/{dbname}'.format(
                **self.get_dsn_parameters())

    def _record(self, msg, query, duration):
        extra = collections.OrderedDict()

        if duration > self._mintime:
            self._add_extra(extra, query, duration)
            self.logger.info('slow ' + msg, extra=extra)

        def processor(data):
            if not data['data']:
                self._add_extra(data['data'], query, duration)
            data['data']['query'] = prettify_sql(data['data']['query'])

        breadcrumb = dict(
            message=msg, category='sql', data=extra, processor=processor)

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
