
##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import sys

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
        s = socket.socket()
        s.connect(('some-host-name-that-will-not-resolve.com', 54321))
    except Exception as e:
        exc = e

    assert util.get_errno_fields(exc) == {
        'errno': 'EAI_NONAME',
        'strerror': 'Name or service not known',
    }
