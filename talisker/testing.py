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

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
__metaclass__ = type

from contextlib import contextmanager
import functools
from datetime import datetime
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

import requests

from talisker.context import Context, ContextId, CONTEXT_MAP
import talisker.logs
import talisker.requests
import talisker.sentry
import talisker.statsd
import talisker.util


__all__ = [
    'configure_testing',
    'clear_all',
    'TestContext',
]

HAVE_DJANGO_INSTALLED = talisker.util.pkg_is_installed('django')
TEST_SENTRY_DSN = 'http://user:pass@host/project'

if sys.version_info[0] == 2:
    def temp_file():
        return tempfile.NamedTemporaryFile('wb', bufsize=0)
else:
    def temp_file():
        return tempfile.NamedTemporaryFile('wb', buffering=0)


def clear_all():
    """Clear all talisker state."""
    ContextId.set(None)
    CONTEXT_MAP.clear()
    talisker.requests.clear()  # talisker requests.Session cache
    talisker.sentry.clear()  # sentry per-request state
    talisker.util.clear_globals()  # module caches
    talisker.util.clear_context_locals()  # any remaining contexts


def configure_testing():
    """Set up a null handler for logging and testing sentry remote."""
    talisker.logs.configure_test_logging()
    talisker.sentry.configure_testing(TEST_SENTRY_DSN)


def reset_prometheus(getpid=os.getpid):
    """Reset prometheus file cache.

    MultiProcessValue keeps a files cache which is only accessible via
    a closure. So the only way to clear the cache is to recreate the closure,
    which is what we do here.
    """
    try:
        from prometheus_client import values
        values.ValueClass = values.MultiProcessValue(getpid)
    except ImportError:
        pass  # prometheus is optional


@contextmanager
def request_id(_id):
    old = Context.request_id
    Context.request_id = _id
    yield
    Context.request_id = old


class LogRecordList(list):
    """A container for searching a list of logging.LogRecords."""
    _sentinel = object()

    def _clean_kwargs(self, kwargs):
        # some UX tweaks
        # shortcut for level, so we can do e.g. level=logging.INFO,
        level = kwargs.pop('level', None)
        if level is not None:
            if isinstance(level, str):
                kwargs['levelname'] = level.upper()
            else:
                kwargs['levelno'] = level
        # you can case levelname either way
        elif 'levelname' in kwargs:
            kwargs['levelname'] = kwargs['levelname'].upper()

    def _match(self, record, extra, kwargs):
        _s = self._sentinel

        def cmp(a, b):
            if a == b:
                return True
            # partial match for strings
            try:
                return b in a
            except Exception:
                return False

        if all(cmp(getattr(record, k, _s), v) for k, v in kwargs.items()):
            if extra:
                get = record.extra.get
                if all(cmp(get(k, _s), v) for k, v in extra.items()):
                    return True
            else:
                return True
        else:
            return False

    def filter(self, extra=None, **kwargs):
        """Search for records matching the query parameters.

        The query parameters are attributes of the logging.LogRecord instance,
        or also the generic 'level' parameter, as shorthand for
        record.levelname or record.levelno. The `extra` dict is compared
        against the LogRecord's extra dict also.

        Matching is partial for strings (i.e. if a in b).
        """
        self._clean_kwargs(kwargs)
        found = self.__class__()
        for record in self:
            if self._match(record, extra, kwargs):
                found.append(record)
        return found

    def find(self, extra=None, **kwargs):
        """Return the first record that matches the query parameters.

        Accepts the same parameters as filter()"""
        self._clean_kwargs(kwargs)
        for record in self:
            if self._match(record, extra, kwargs):
                return record

    def exists(self, extra=None, **kwargs):
        """Return true if the matching log message exists."""
        return self.find(extra, **kwargs) is not None

    def match(self, record, extra=None, **kwargs):
        """Match an single record, same as parameters to filter()."""
        self._clean_kwargs(kwargs)
        return self._match(record, extra, kwargs)

    def assert_log(self, **kwargs):
        if not self.exists(**kwargs):
            # evaluate each term independently to narrow down culprit
            terms = []
            extra = kwargs.pop('extra', {})
            for kw, value in kwargs.items():
                if len(self.filter(**{kw: value})) == 0:
                    terms.append((kw, value))
            for kw, value in extra.items():
                if len(self.filter(**{'extra': {kw: value}})) == 0:
                    terms.append(('extra["' + kw + '"]', value))

            desc = '\n'.join('    {}={}'.format(k, v) for k, v in terms)
            raise AssertionError(
                'Could not find log out of {} logs.\n'
                'Search terms that could not be found:\n'
                '{}'.format(len(self), desc)
            )

    def assert_not_log(self, **kwargs):
        if self.exists(**kwargs):
            desc = '\n    '.join(
                '{}={!r}'.format(k, v) for k, v in sorted(kwargs.items())
            )
            raise AssertionError(
                'Found log matching the following:\n    {}'.format(desc)
            )

    TIMESTAMP = re.compile(r'^\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d.\d\d\dZ')

    @classmethod
    def parse(cls, lines):
        self = cls()
        current = []
        for line in lines:
            if line.strip():
                if cls.TIMESTAMP.match(line):
                    if current:
                        self.append(self._parse_line(current))
                    current = []
                current.append(line)
        if current:
            self.append(self._parse_line(current))
        return self

    def _parse_line(self, lines):
        """Stupid simple logfmt parser"""
        log = lines[0]
        trailer = lines[1:]
        parsed = shlex.split(log)
        try:
            date, tod, level, name, msg = parsed[:5]
            extra = dict((v.split('=', 1)) for v in parsed[5:])
        except ValueError:
            raise AssertionError(
                "failed to parse logfmt:\n" + '\n'.join(lines)
            )

        # create a minimal LogRecord to search against
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname=None,
            lineno=None,
            msg=msg,
            args=None,
            exc_info=None,
        )
        dt = datetime.strptime(date + "T" + tod, "%Y-%m-%dT%H:%M:%S.%fZ")
        ts = time.mktime(dt.timetuple())  # needed py2 support
        record.message = msg
        record.extra = extra
        record.created = ts
        record.msecs = (ts - int(ts)) * 1000
        record.trailer = '\n'.join(trailer)
        return record


class TestHandler(logging.Handler):
    """Testing handler that records its logs in memory."""
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.records = LogRecordList()
        self.lines = []

    def emit(self, record):
        self.records.append(record)
        # formatting forces the setting of record.message
        self.lines.extend(self.format(record).split('\n'))


def get_sentry_messages(client=None):
    """Gets test sentry messages.

    Returns None if sentry not enabled."""
    if not talisker.sentry.enabled:
        return None
    if client is None:
        client = talisker.sentry.get_client()
    transport = client.remote.get_transport()
    if transport is None:
        return None
    else:
        return transport.messages


class TestContext():

    def __init__(self, name=None):
        if name is None:
            self.name = str(uuid.uuid4())
        else:
            self.name = name

        self.dsn = TEST_SENTRY_DSN + self.name
        self.handler = TestHandler()
        self.statsd_client = talisker.statsd.DummyClient(collect=True)
        self.sentry_context = talisker.sentry.TestSentryContext(self.dsn)

    def start(self):
        self.old_statsd = talisker.statsd.get_client.raw_update(
            self.statsd_client)
        talisker.logs.add_talisker_handler(logging.NOTSET, self.handler)
        self.sentry_context.start()
        Context.new()

    def stop(self):
        logging.getLogger().handlers.remove(self.handler)
        talisker.statsd.get_client.raw_update(self.old_statsd)
        self.sentry_context.stop()
        clear_all()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.stop()

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper

    @property
    def logs(self):
        return self.handler.records

    @property
    def sentry(self):
        return self.sentry_context.messages

    @property
    def statsd(self):
        return self.statsd_client.stats

    def assert_log(self, **kwargs):
        self.logs.assert_log(**kwargs)

    def assert_not_log(self, **kwargs):
        self.logs.assert_not_log(**kwargs)


class ServerProcessError(Exception):
    pass


class ServerProcess(object):
    """Context mananger to run a server subprocess """
    def __init__(self, cmd, env=None, **kwargs):
        self.cmd = cmd
        self.env = env
        self.kwargs = kwargs
        self.output = []
        self.ps = None
        self._log = None

    def start(self):
        self.output_file = temp_file()
        self.reader = open(self.output_file.name, 'r')

        if self.env is None:
            env = os.environ.copy()
        else:
            env = self.env.copy()

        if 'PYTHONUNBUFFERED' not in env:
            env['PYTHONUNBUFFERED'] = '1'

        self.ps = subprocess.Popen(
            self.cmd,
            bufsize=0,
            stdout=self.output_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            universal_newlines=True,
            env=env,
            **self.kwargs
        )
        try:
            self.check()
        except Exception:
            self.close(error=True)
            raise

    def close(self, error=False):
        """Clean up process."""
        if not self.finished:
            self.ps.terminate()
            self.ps.wait()

        if not self.reader.closed:
            for line in self.reader.readlines():
                self.output.append(line.rstrip())
            self.reader.close()

        if error:
            # just dump the output to stderr for now, for visibility
            sys.stderr.write('Server process died:\n')
            sys.stderr.write('\n'.join(self.output))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.close(error=exc_type is not None)

    @property
    def finished(self):
        return self.ps is not None and self.ps.poll() is not None

    @property
    def log(self):
        assert self.finished
        if self._log is None:
            self._log = LogRecordList.parse(self.output)
        return self._log

    def check(self):
        """Check the server process is still running or has finished."""
        rc = self.ps.poll()
        if rc is not None and rc > 0:
            raise ServerProcessError('subprocess errored')

    def readline(self, timeout=30, delay=0.1):
        if not self.output_file.closed:
            self.output_file.flush()

        start = time.time()
        line = self.reader.readline()

        while time.time() - start < timeout and line == '':
            self.check()
            time.sleep(delay)
            line = self.reader.readline()

        if line == '':
            raise Exception(
                'could not read line from process stdout '
                'within timeout of {}'.format(timeout))

        self.output.append(line.rstrip())
        return timeout - (time.time() - start)

    def wait_for_output(self, target, timeout, delay=0.1):
        try:
            # read first line if needed
            if len(self.output) == 0:
                self.readline(timeout, delay)

            # maybe we already got there
            for line in self.output:
                if target in line:
                    return

            while target not in self.output[-1]:
                self.readline(timeout, delay)

        except Exception:
            self.close(error=True)
            raise


class GunicornProcess(ServerProcess):
    """Context mananger to run Talisker's gunicorn server.

    It captures all output, and waits untill it sees which port gunicorn is
    listening on, expose as url attribute.
    """

    ADDRESS = re.compile(r'http://(127\.0\.0\.\d):(\d+)')
    WORKER = 'Booting worker with pid'

    def __init__(self,
                 app,
                 args=None,
                 env=None,
                 gunicorn='talisker.gunicorn',
                 ip='127.0.0.1',
                 **kwargs):

        self.app = app
        self.ip = ip
        self.bindings = {}
        cmd = [
            gunicorn,
            '--bind', ip + ':0',
        ]
        if args:
            cmd.extend(args)
        cmd.append(app)
        super().__init__(cmd, env=env, **kwargs)

    def start(self):
        super().start()

        self.wait_for_output(self.WORKER, timeout=30)
        for line in self.output:
            for ip, port in self.ADDRESS.findall(line):
                self.bindings[ip] = port

        if not self.bindings:
            raise Exception('could not parse gunicorn port from output')

        # check that the app has loaded and gunicorn has not died before
        # returning control.
        try:
            self.ping()
        except Exception:
            self.close(error=True)
            raise

    def url(self, path, iface=None):
        if iface is None:
            iface = self.ip
        port = self.bindings[iface]
        return 'http://{}:{}{}'.format(iface, port, path)

    def ping(self):
        success = False
        try:
            r = requests.get(self.url('/_status/ping'))
            success = r.status_code == 200
        except requests.exceptions.RequestException:
            pass

        if not success:
            raise ServerProcessError(
                'could not ping server at {}'.format(self.url('/')),
            )


def run_wsgi(app, environ):
    """Execute a wsgi application, returning (body, status, headers)."""
    output = {}

    def start_response(status, headers, exc_info=None):
        output['status'] = status
        output['headers'] = headers

    body = app(environ, start_response)

    return body, output['status'], output['headers']
