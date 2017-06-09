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

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
import sys
import subprocess
import re
import shlex
import logging
from contextlib import contextmanager
import weakref

import requests

import talisker.logs


class TestLogger(talisker.logs.StructuredLogger):

    def __init__(self, name):
        super().__init__(name)
        self.records = []
        self.lines = []


class TestHandler(logging.Handler):
    """Testing handler that records its logs in memory."""
    def __init__(self, logger, level=logging.NOTSET):
        assert isinstance(logger, TestLogger)
        super().__init__(level)
        self.logger = weakref.proxy(logger)

    def emit(self, record):
        self.logger.records.append(record)
        self.logger.lines.extend(self.format(record).split('\n'))


def test_logger():
    logger = TestLogger('test')
    handler = TestHandler(logger)
    handler.setFormatter(talisker.logs.StructuredFormatter())
    handler.setLevel(logging.NOTSET)
    logger.addHandler(handler)
    return logger


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
        date, time, level, name, msg = parsed[:5]
        try:
            extra = dict((v.split('=')) for v in parsed[5:])
        except:
            assert 0, "failed to parse logfmt: " + log
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
            all(k in haystack for k in needle) and
            all(needle[k] in haystack[k] for k in needle)
        )

    def exists(self, extra=None, trailer=None, **kwargs):
        for log in self.logs:
            strings_match = self._compare_strings(kwargs, log)
            if extra is not None:
                extra_match = self._compare_strings(extra, log['extra'])
            else:
                extra_match = True
            if trailer is not None:
                trailer_match = True
                for line in trailer:
                    if not any(line in tline for tline in log['trailer']):
                        trailer_match = False
                        break
            else:
                trailer_match = True
            if strings_match and extra_match and trailer_match:
                return True
        return False

    def __contains__(self, params):
        return self.exists(**params)


class ServerProcessError(Exception):
    pass


class ServerProcess:
    """Context mananger to run a server subprocess """

    _log = None

    def __init__(self, cmd):
        self.cmd = cmd
        self.output = []
        self.ps = None

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

    @contextmanager
    def _handle_enter_exception(self):
        """Helper to manually handle an exception in the __enter__ method"""
        try:
            yield
        except:
            suppressed = self.__exit__(*sys.exc_info())
            if not suppressed:
                raise

    def __enter__(self):
        self.ps = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        with self._handle_enter_exception():
            self.check()

    def __exit__(self, type=None, value=None, traceback=None):
        if not self.finished:
            self.ps.terminate()

        # ensure all output is read
        self.output.extend(self.ps.stdout)

        # just dump the output to stderr for now, for visibility
        # might be a way to include it in the exception somehow
        if type is ServerProcessError:
            sys.stderr.write('Server process died:\n')
            sys.stderr.write(''.join(self.output))


class GunicornProcess(ServerProcess):
    """Context mananger to run Talisker's gunicorn server.

    It captures all output, and waits till it sees gunicorn which port
    guncicorn is listening on, expose as url attribute.
    """

    ADDRESS = re.compile(r'http://127\.0\.0\.1:(\d+)')
    WORKER = 'Booting worker with pid'

    def __init__(self, app, ip='127.0.0.1', args=None):
        self.app = app
        self.ip = ip
        self.port = None
        cmd = [
            'env/bin/talisker.gunicorn',  # TODO avoid hardcoding the path
            '--bind', ip + ':0',
            '--access-logfile', '-',
        ]
        if args:
            cmd.extend(args)
        cmd.append(app)
        super().__init__(cmd)

    def __enter__(self):
        super().__enter__()
        self.output.append(self.ps.stdout.readline())
        while self.WORKER not in self.output[-1]:
            with self._handle_enter_exception():
                self.check()
            m = self.ADDRESS.search(self.output[-1])
            if m:
                self.port = m.groups()[0]
            self.output.append(self.ps.stdout.readline())

        if self.port is None:
            raise Exception(
                'could not parse gunicorn port from output',
                extra={'trailer': ''.join(self.output)},
            )

        # check that the app has loaded and gunicorn has not died
        with self._handle_enter_exception():
            self.check()
            self.ping()

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
