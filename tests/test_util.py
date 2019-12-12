
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

import os
import sys
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


# hide these from pytest's collection when running under py2
if sys.version_info[0] > 2:
    from tests.py3_test_util import (  # NOQA
        test_get_root_exception_implicit,
        test_get_root_exception_explicit,
        test_get_root_exception_mixed,
    )


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
        assert processed_exc == {
            'errno': 'EAI_NONAME',
            'strerror': 'Name or service not known'
        }


def test_local():
    local = util.Local()
    local.test = 1

    if os.fork() == 0:
        assert not hasattr(local, 'test')
        os._exit(0)
