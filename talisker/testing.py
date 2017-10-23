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

import requests

import talisker.logs


class TestHandler(logging.Handler):
    """Testing handler that records its logs in memory."""
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.records = []
        self.lines = []

    def emit(self, record):
        self.records.append(record)
        self.lines.extend(self.format(record).split('\n'))


class TestLogger(talisker.logs.StructuredLogger):
    def __init__(self, name='test'):
        super().__init__(name)
        handler = TestHandler()
        handler.setFormatter(talisker.logs.StructuredFormatter())
        handler.setLevel(logging.NOTSET)
        self.addHandler(handler)
        self._test_handler = handler

    @property
    def records(self):
        return self._test_handler.records

    @property
    def lines(self):
        return self._test_handler.lines


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
            extra = dict((v.split('=', 1)) for v in parsed[5:])
        except ValueError:
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
    def __init__(self, cmd, env=None):
        self.cmd = cmd
        self.env = env
        self.output = []
        self.ps = None
        self._log = None

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

    def close(self, error=False):
        """Clean up process."""
        if not self.finished:
            self.ps.terminate()
            self.ps.wait()

        # ensure all output is read
        self.output.extend(self.ps.stdout)

        if error:
            # just dump the output to stderr for now, for visibility
            sys.stderr.write('Server process died:\n')
            sys.stderr.write(''.join(self.output))

    def start(self):
        self.ps = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=self.env
        )
        try:
            self.check()
        except Exception:
            self.close(error=True)
            raise

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.close(error=exc_type is not None)


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
                 ip='127.0.0.1'):
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
        super().__init__(cmd, env=env)

    def start(self):
        super().start()
        self.output.append(self.ps.stdout.readline())

        try:
            self.check()
            while self.WORKER not in self.output[-1]:
                self.check()
                m = self.ADDRESS.search(self.output[-1])
                if m:
                    self.port = m.groups()[0]
                self.output.append(self.ps.stdout.readline())

        except Exception:
            self.close(error=True)
            raise

        if self.port is None:
            raise Exception(
                'could not parse gunicorn port from output',
                extra={'trailer': ''.join(self.output)},
            )

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
