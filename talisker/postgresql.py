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
import shlex

from psycopg2.extensions import cursor, connection

try:
    from sqlparse import format as format_sql
except ImportError:
    def format_sql(sql, *args, **kwargs):
        return sql

import raven.breadcrumbs

import talisker
from talisker.util import get_rounded_ms
from talisker.context import track_request_metric

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
            self._threshold = talisker.get_config().slowquery_threshold
        return self._threshold

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', TaliskerCursor)
        return super().cursor(*args, **kwargs)

    def _format_query(self, query):
        if callable(query):
            query = query()
        query = prettify_sql(query)
        query = FILTERED if query is None else query
        return query

    def _record(self, msg, query, duration):
        track_request_metric('sql', duration)

        if self.query_threshold >= 0 and duration > self.query_threshold:
            extra = collections.OrderedDict()
            extra['trailer'] = self._format_query(query)
            extra['duration_ms'] = duration
            extra['connection'] = get_safe_connection_string(self)
            self.logger.info('slow ' + msg, extra=extra)

        def processor(data):
            data['data']['query'] = self._format_query(query)
            data['data']['duration'] = duration
            data['data']['connection'] = get_safe_connection_string(self)

        breadcrumb = dict(
            message=msg, category='sql', data={}, processor=processor)

        raven.breadcrumbs.record(**breadcrumb)


class TaliskerCursor(cursor):

    def execute(self, query, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).execute(query, vars)
        finally:
            duration = get_rounded_ms(timestamp)
            if vars is None:
                query = None
            self.connection._record('query', query, duration)

    def callproc(self, procname, vars=None):
        timestamp = time.time()
        try:
            return super(TaliskerCursor, self).callproc(procname, vars)
        finally:
            duration = get_rounded_ms(timestamp)
            # no query parameters, cannot safely record
            self.connection._record(
                'stored proc: {}'.format(procname), None, duration)
