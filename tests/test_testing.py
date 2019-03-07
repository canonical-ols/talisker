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
import logging
import sys
import textwrap

import pytest
import requests

import talisker.logs
from talisker import testing


def test_log_record_list():

    makeRecord = talisker.logs.StructuredLogger('test').makeRecord

    def record(name, level, msg, extra={}):
        return makeRecord(name, level, 'fn', 123, msg, None, None, extra=extra)

    r1 = record('root.log1', logging.INFO, 'foo msg')
    r2 = record('root.log1', logging.DEBUG, 'bar')
    r3 = record('root.log2', logging.WARNING, 'baz', extra={'a': 1})

    records = testing.LogRecordList()
    records.extend([r1, r2, r3])

    # name, ex
    assert records.filter(name='root.log1') == [r1, r2]
    assert records.filter(name='log1') == [r1, r2]
    assert records.filter(name='root') == [r1, r2, r3]

    # msg
    assert records.filter(msg='msg') == [r1]
    assert records.filter(msg='bar') == [r2]

    # level
    assert records.filter(name='log1', level=logging.INFO) == [r1]
    assert records.filter(name='log1', levelname='INFO') == [r1]
    assert records.filter(name='log1').filter(level=logging.DEBUG) == [r2]

    # extra
    assert records.filter(extra={'a': 1}) == [r3]
    assert records.filter(extra={'a': 2}) == []


def test_test_context():

    assert testing.get_sentry_messages() == []

    logger = logging.getLogger('test_test_context')
    with testing.TestContext() as ctx:
        logger.info('foo', extra={'a': 1})
        logger.warning('bar', extra={'b': 2})
        talisker.statsd.get_client().timing('statsd', 3)
        talisker.sentry.get_client().capture(
            'Message',
            message='test',
            extra={
                'foo': 'bar'
            },
        )

    ctx.assert_log(
        name=logger.name, msg='foo', level='info', extra={'a': 1})
    ctx.assert_log(
        name=logger.name, msg='bar', level='warning', extra={'b': 2})

    with pytest.raises(AssertionError) as exc:
        ctx.assert_log(name=logger.name, msg='XXX', level='info')

    assert str(exc.value) == textwrap.dedent("""
        Could not find log out of 3 logs:
            msg={0}'XXX' (0 matches)
            level={0}'info' (1 matches)
            name='test_test_context' (2 matches)
    """).strip().format('u' if sys.version_info[0] == 2 else '')

    with pytest.raises(AssertionError) as exc:
        ctx.assert_not_log(name=logger.name, msg='foo', level='info')

    assert str(exc.value) == textwrap.dedent("""
        Found log matching the following:
            level={0}'info'
            msg={0}'foo'
            name='test_test_context'
    """).strip().format('u' if sys.version_info[0] == 2 else '')

    assert ctx.statsd == ['statsd:3.000000|ms']

    # ensure there are not sentry messages left over
    assert testing.get_sentry_messages() == []
    assert len(ctx.sentry) == 1
    assert ctx.sentry[0]['message'] == 'test'
    # check that extra values have been decoded correctly
    assert ctx.sentry[0]['extra']['foo'] == 'bar'


def test_logoutput():
    handler = testing.TestHandler()
    handler.setFormatter(talisker.logs.StructuredFormatter())
    handler.setLevel(logging.NOTSET)
    logger = talisker.logs.StructuredLogger('test')
    logger.addHandler(handler)

    logger.info('msg 1')
    logger.info('msg 2 with extra', extra={'foo': 'barrrrr'})
    logger.info(
        'msg 3 with tailer', extra={'trailer': 'line1\nline2\nline3'})
    log = testing.LogOutput(handler.lines)
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
    try:
        import gunicorn  # noqa
    except ImportError:
        pytest.skip('need gunicorn installed')
    id = 'test-id'
    ps = testing.GunicornProcess('tests.wsgi_app')
    with ps:
        r = requests.get(ps.url('/'), headers={'X-Request-Id': id})
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
    } in ps.log


def test_gunicornprocess_bad_app():
    gunicorn = testing.GunicornProcess('no_app_here')
    with pytest.raises(testing.ServerProcessError):
        with gunicorn:
            pass
