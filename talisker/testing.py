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

import ast
import functools
import logging
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
import zlib

import raven
import requests

import talisker.context
import talisker.logs
import talisker.requests
import talisker.statsd
import talisker.util


__all__ = [
    'configure_testing',
    'clear_all'
    'TestContext',
]

HAVE_DJANGO_INSTALLED = talisker.util.pkg_is_installed('django')

if sys.version_info[0] == 2:
    def temp_file():
        return tempfile.NamedTemporaryFile('wb', bufsize=0)
else:
    def temp_file():
        return tempfile.NamedTemporaryFile('wb', buffering=0)


def clear_all():
    """Clear all talisker state."""
    talisker.context.clear()  # talisker request_context
    talisker.requests.clear()  # talisker requests.Session cache
    talisker.sentry.clear()  # sentry per-request state
    talisker.util.clear_globals()  # module caches
    talisker.util.clear_context_locals()  # any remaining contexts
    clear_sentry_messages()


def configure_testing():
    """Set up a null handler for logging and testing sentry remote."""
    talisker.logs.configure_test_logging()
    configure_sentry_client()


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


class DummySentryTransport(raven.transport.Transport):
    """Fake sentry transport for testing."""
    scheme = ['test']

    def __init__(self, *args, **kwargs):
        self.messages = []

    def send(self, *args, **kwargs):
        # In raven<6, args = (data, headers).
        # In raven 6.x args = (url, data, headers)
        if len(args) == 2:
            data, _ = args
        elif len(args) == 3:
            _, data, _ = args
        else:
            raise Exception('raven Transport.send api seems to have changed')
        raw = json.loads(zlib.decompress(data).decode('utf8'))
        # to make asserting easier, parse json strings into python strings
        for k, v in list(raw['extra'].items()):
            try:
                val = ast.literal_eval(v)
            except Exception:
                pass
            else:
                raw['extra'][k] = val

        self.messages.append(raw)


def clear_sentry_messages():
    messages = get_sentry_messages()
    if messages is not None:
        # py2.7 doesn't have list.clear() :(
        messages[:] = []


def get_sentry_messages(client=None):
    if client is None:
        client = talisker.sentry.get_client()
    transport = client.remote.get_transport()
    if transport is None:
        return None
    else:
        return transport.messages


TEST_SENTRY_DSN = 'http://user:pass@host/project'


def configure_sentry_client(client=None):
    client = talisker.sentry.get_client()
    client.set_dsn(TEST_SENTRY_DSN, transport=DummySentryTransport)


class TestContext():

    def __init__(self, name=None):
        if name is None:
            self.name = str(uuid.uuid4())
        else:
            self.name = name

        self.dsn = TEST_SENTRY_DSN + self.name
        self.handler = TestHandler()
        self.statsd_client = talisker.statsd.DummyClient(collect=True)
        self.sentry_client = talisker.sentry.get_client()
        self.sentry_remote = self.sentry_client.remote

    def start(self):
        self.old_statsd = talisker.statsd.get_client.raw_update(
            self.statsd_client)
        self.sentry_client.set_dsn(self.dsn, transport=DummySentryTransport)
        self.sentry_transport = self.sentry_client.remote.get_transport()
        talisker.logs.add_talisker_handler(logging.NOTSET, self.handler)

    def stop(self):
        logging.getLogger().handlers.remove(self.handler)
        talisker.statsd.get_client.raw_update(self.old_statsd)
        # restore the original sentry remote
        self.sentry_client.remote = self.sentry_remote
        self.sentry_client._transport_cache.pop(self.dsn, None)
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
        return self.sentry_transport.messages

    @property
    def statsd(self):
        return self.statsd_client.stats

    def assert_log(self, **kwargs):
        if not self.logs.exists(**kwargs):
            # evaluate each term independently to narrow down culprit
            terms = []
            for kw, value in kwargs.items():
                num = len(self.logs.filter(**{kw: value}))
                terms.append((num, kw, value))
            terms.sort()  # 0 matches go first, as likely to be the issue

            desc = '\n    '.join(
                '{1}={2!r} ({0} matches)'.format(*t) for t in terms
            )
            raise AssertionError(
                'Could not find log out of {} logs:\n    {}'.format(
                    len(self.logs), desc))

    def assert_not_log(self, **kwargs):
        if self.logs.exists(**kwargs):
            desc = '\n    '.join(
                '{}={!r}'.format(k, v) for k, v in sorted(kwargs.items())
            )
            raise AssertionError(
                'Found log matching the following:\n    {}'.format(desc)
            )


class LogOutput:
    """A container for log messages output by a Talisker program.

    Parses log lines, and makes them available for inspection in tests.
    """

    TIMESTAMP = re.compile(r'^\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d.\d\d\dZ')

    def __init__(self, lines):
        self.logs = list(self.read(lines))

    def read(self, lines):
        current = []
        for line in lines:
            if line.strip():
                if self.TIMESTAMP.match(line):
                    if current:
                        yield self.parse(current)
                    current = []
                current.append(line)
        if current:
            yield self.parse(current)

    def parse(self, logs):
        """Stupid simple logfmt parser"""
        log = logs[0]
        trailer = logs[1:]
        parsed = shlex.split(log)
        try:
            date, time, level, name, msg = parsed[:5]
            extra = dict((v.split('=', 1)) for v in parsed[5:])
        except ValueError:
            assert 0, "failed to parse logfmt:\n" + '\n'.join(logs)
        return {
            'ts': date + " " + time,
            'level': level,
            'logger': name,
            'logmsg': msg,
            'extra': extra,
            'trailer': trailer,
        }

    def _compare_strings(self, needle, haystack):
        return (
            all(k in haystack for k in needle)
            and all(needle[k] in haystack[k] for k in needle)
        )

    def exists(self, **match):
        extra = match.pop('extra', None)
        trailer = match.pop('trailer', None)
        for log in self.logs:
            strings_match = self._compare_strings(match, log)
            extra_match = trailer_match = True

            if extra is not None:
                extra_match = self._compare_strings(extra, log['extra'])

            if trailer is not None:
                for line in trailer:
                    if not any(line in tline for tline in log['trailer']):
                        trailer_match = False
                        break

            if strings_match and extra_match and trailer_match:
                return True

        return False

    def __contains__(self, params):
        return self.exists(**params)


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
            self._log = LogOutput(self.output)
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

    ADDRESS = re.compile(r'http://127\.0\.0\.1:(\d+)')
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
        self.port = None
        cmd = [
            gunicorn,
            '--bind', ip + ':0',
            '--access-logfile', '-',
        ]
        if args:
            cmd.extend(args)
        cmd.append(app)
        super().__init__(cmd, env=env, **kwargs)

    def start(self):
        super().start()

        self.wait_for_output(self.WORKER, timeout=30)
        for line in self.output:
            m = self.ADDRESS.search(line)
            if m:
                self.port = m.groups()[0]

        if self.port is None:
            raise Exception('could not parse gunicorn port from output')

        # check that the app has loaded and gunicorn has not died before
        # returning control.
        try:
            self.ping()
        except Exception:
            self.close(error=True)
            raise

    def url(self, path):
        return 'http://{}:{}{}'.format(self.ip, self.port, path)

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
