
#
# Copyright (c) 2015-2021 Canonical, Ltd.
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

import os
import threading
import time

from freezegun import freeze_time
from talisker import util


def test_sanitize_url():
    source = 'https://user:pass@host/path?q=bar'
    expected = 'https://user:********@host/path?'
    assert util.sanitize_url(source) == expected

    # with port
    assert (
        util.sanitize_url('https://host:1234/path') == 'https://host:1234/path'
    )

    # no user
    assert util.sanitize_url('https://host/path') == 'https://host/path'


@freeze_time('2016-01-02 03:04:05.1234')
def test_get_rounded_ms():
    assert util.get_rounded_ms(time.time() - 1.0) == 1000
    assert util.get_rounded_ms(time.time() - 123.0) == 123000
    assert util.get_rounded_ms(time.time() - 0.123) == 123
    assert util.get_rounded_ms(time.time() - 0.123456789) == 123.457
    assert util.get_rounded_ms(0.1, 0.3) == 200.0


def test_get_root_exception_implicit():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception:
                raise Exception('one')
        except Exception:
            raise Exception('two')
    except Exception as e:
        exc = e

    root = util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_root_exception_explicit():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception as a:
                raise Exception('one') from a
        except Exception as b:
            raise Exception('two') from b
    except Exception as c:
        exc = c
    root = util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_root_exception_mixed():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception as a:
                raise Exception('one') from a
        except Exception:
            raise Exception('two')
    except Exception as e:
        exc = e
    root = util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_errno_fields_permissions():
    exc = None
    try:
        open('/blah', 'w')
    except Exception as e:
        exc = e

    assert util.get_errno_fields(exc) == {
        'errno': 'EACCES',
        'strerror': 'Permission denied',
        'filename': '/blah',
    }


def test_get_errno_fields_connection():
    exc = None
    try:
        import socket
        s = socket.socket()
        s.connect(('localhost', 54321))
    except Exception as e:
        exc = e

    assert util.get_errno_fields(exc) == {
        'errno': 'ECONNREFUSED',
        'strerror': 'Connection refused',
    }


def test_get_errno_fields_dns():
    exc = None
    try:
        import socket
        import platform
        s = socket.socket()
        s.connect(('some-host-name-that-will-not-resolve.com', 54321))
    except Exception as e:
        exc = e

    processed_exc = util.get_errno_fields(exc)
    if platform.system() == 'Darwin':
        assert processed_exc == {
            'errno': 'ENOEXEC',
            'strerror': 'nodename nor servname provided, or not known'
        }
    else:
        assert processed_exc in [{
            'errno': 'EAI_NONAME',
            'strerror': 'Name or service not known'
        }, {
            'errno': 'EAI_NODATA',
            'strerror': 'No address associated with hostname'
        }]


def test_local_forking():
    local = util.Local()
    local.test = 1

    if os.fork() == 0:
        assert not hasattr(local, 'test')
        local.test = 2
        assert local.test == 2
        os._exit(0)


def test_local_threading():
    local = util.Local()
    local.test = 1

    thread_results = {}

    def f(results):
        results['no_attr'] = not hasattr(local, 'test')
        try:
            local.test = 2
        except Exception:
            pass
        else:
            results['new_attr'] = local.test

    thread = threading.Thread(target=f, args=(thread_results,))
    thread.start()
    thread.join(timeout=1.1)

    assert local.test == 1
    assert thread_results['no_attr']
    assert thread_results['new_attr'] == 2
