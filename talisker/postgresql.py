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

import collections
import logging
import time

import psycopg2
from psycopg2.extensions import cursor, connection

try:
    from sqlparse import format as format_sql
except ImportError:
    def format_sql(sql, *args, **kwargs):
        return sql

import talisker
from talisker.util import get_rounded_ms
import talisker.sentry

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


class TaliskerConnection(connection):
    _logger = None
    _threshold = None
    _explain = None
    _safe_dsn = None
    _safe_dsn_format = '{user}@{host}:{port}/{dbname}'

    @property
    def safe_dsn(self):
        if self._safe_dsn is None:
            try:
                params = self.get_dsn_parameters()
                params.setdefault('host', 'localhost')
                self._safe_dsn = self._safe_dsn_format.format(**params)
            except Exception:
                self.logger.exception('Failed to parse DSN')
                self._safe_dsn = 'could not parse dsn'

        return self._safe_dsn

    @property
    def logger(self):
        if self._logger is None:
            self._logger = logging.getLogger('talisker.slowqueries')
        return self._logger

    @property
    def query_threshold(self):
        if self._threshold is None:
            self._threshold = talisker.get_config().slowquery_threshold
        return self._threshold

    @property
    def explain_breadcrumbs(self):
        if self._explain is None:
            self._explain = talisker.get_config().explain_sql
        return self._explain

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', TaliskerCursor)
        return super().cursor(*args, **kwargs)

    def _format_query(self, query, vars):
        if callable(query):
            query = query()
        query = prettify_sql(query)
        if query is None or vars is None:
            return FILTERED
        return query

    def _record(self, msg, query, vars, duration, extra={}):
        talisker.Context.track('sql', duration)

        qdata = collections.OrderedDict()
        qdata['duration_ms'] = duration
        qdata['connection'] = self.safe_dsn
        qdata.update(extra)

        # grab a reference here, where super() works
        base_connection = super()

        if self.query_threshold >= 0 and duration > self.query_threshold:
            formatted = self._format_query(query, vars)
            self.logger.info(
                'slow ' + msg, extra=dict(qdata, trailer=formatted))

        def processor(data):
            qdata['query'] = self._format_query(query, vars)
            if self.explain_breadcrumbs or talisker.Context.debug:
                try:
                    cursor = base_connection.cursor()
                    cursor.execute('EXPLAIN ' + query, vars)
                    plan = '\n'.join(l[0] for l in cursor.fetchall())
                    qdata['plan'] = plan
                except Exception as e:
                    qdata['plan'] = 'could not explain query: ' + str(e)

            data['data'].update(qdata)

        breadcrumb = dict(
            message=msg, category='sql', data={}, processor=processor)

        talisker.sentry.record_breadcrumb(**breadcrumb)


class TaliskerCursor(cursor):

    def apply_timeout(self):
        ctx_timeout = talisker.Context.deadline_timeout()
        if ctx_timeout is None:
            return None

        ms = int(ctx_timeout * 1000)
        super().execute(
            'SET LOCAL statement_timeout TO %s', (ms,)
        )
        return ms

    def execute(self, query, vars=None):
        extra = collections.OrderedDict()
        timeout = self.apply_timeout()
        if timeout is not None:
            extra['timeout'] = timeout
        timestamp = time.time()
        try:
            return super().execute(query, vars)
        except psycopg2.OperationalError as exc:
            extra['pgcode'] = exc.pgcode
            extra['pgerror'] = exc.pgerror
            if exc.pgcode == '57014':
                extra['timedout'] = True
            raise
        finally:
            duration = get_rounded_ms(timestamp)
            self.connection._record('query', query, vars, duration, extra)

    def callproc(self, procname, vars=None):
        extra = collections.OrderedDict()
        timeout = self.apply_timeout()
        if timeout is not None:
            extra['timeout'] = timeout
        timestamp = time.time()
        try:
            return super().callproc(procname, vars)
        except psycopg2.OperationalError as exc:
            extra['pgcode'] = exc.pgcode
            extra['pgerror'] = exc.pgerror
            if exc.pgcode == '57014':
                extra['timedout'] = True
            raise
        finally:
            duration = get_rounded_ms(timestamp)
            # no query parameters, cannot safely record
            self.connection._record(
                'stored proc: {}'.format(procname),
                None,
                vars,
                duration,
                extra,
            )
