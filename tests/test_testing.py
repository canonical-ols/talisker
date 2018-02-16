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

import pytest
import requests

from talisker import testing


def test_logoutput():
    logger = testing.TestLogger()
    logger.info('msg 1')
    logger.info('msg 2 with extra', extra={'foo': 'barrrrr'})
    logger.info(
        'msg 3 with tailer', extra={'trailer': 'line1\nline2\nline3'})
    log = testing.LogOutput(logger.lines)
    assert {'logmsg': 'not found'} not in log
    assert {'logmsg': 'msg 1'} in log
    assert {'logmsg': 'msg 1'} in log
    assert {'logmsg': 'msg 1', 'extra': {'foo': 'baz'}} not in log
    assert {'logmsg': 'msg 2'} in log
    assert {'logmsg': 'msg 2', 'extra': {'foo': 'bar'}} in log
    assert {
        'logmsg': 'msg 2',
        'extra': {'foo': 'bar', 'baz': '1'}
    } not in log
    assert {'logmsg': 'msg 3'} in log
    assert {'logmsg': 'msg 3', 'trailer': ['line1']} in log
    assert {'logmsg': 'msg 3', 'trailer': ['line2']} in log


def test_serverprocess_success():
    server = testing.ServerProcess(['true'])
    with server:
        server.ps.wait()
    assert server.finished


def test_serverprocess_failure():
    server = testing.ServerProcess(['false'])
    with pytest.raises(testing.ServerProcessError):
        with server:
            while 1:
                server.check()


def test_serverprocess_output(tmpdir):
    script = tmpdir.join('script.sh')
    script.write("for i in $(seq 20); do echo $i; done")
    server = testing.ServerProcess(['bash', str(script)])
    with server:
        server.ps.wait()
    assert server.output == [str(i) for i in range(1, 21)]


def test_serverprocess_output_wait(tmpdir):
    script = tmpdir.join('script.sh')
    script.write("echo 1; echo 2; echo 'here'; read; echo 3; echo 4;")
    server = testing.ServerProcess(['bash', str(script)])
    with server:
        server.wait_for_output('here', timeout=30)
        assert server.output == ['1', '2', 'here']
        server.ps.stdin.write('bar\n')
        server.ps.wait()

    assert server.output == ['1', '2', 'here', '3', '4']


def test_gunicornprocess_success():
    id = 'test-id'
    gunicorn = testing.GunicornProcess('tests.wsgi_app')
    with gunicorn:
        r = requests.get(gunicorn.url('/'), headers={'X-Request-Id': id})
        assert r.status_code == 200
    assert {
        'logmsg': 'GET /',
        'extra': {
            'status': '200',
            'method': 'GET',
            'ip': '127.0.0.1',
            'proto': 'HTTP/1.1',
            'request_id': id,
        }
    } in gunicorn.log


def test_gunicornprocess_bad_app():
    gunicorn = testing.GunicornProcess('no_app_here')
    with pytest.raises(testing.ServerProcessError):
        with gunicorn:
            pass
