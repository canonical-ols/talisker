
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

import sys
import textwrap

import pytest

import talisker.util


@pytest.mark.skipif(sys.version_info[:2] < (3, 3), reason='>=py3.3 only')
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

    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)


@pytest.mark.skipif(sys.version_info[:2] < (3, 3), reason='>=py3.3 only')
def test_get_root_exception_explicit():
    # have to exec this so we don't break pytest collection under py2
    code = textwrap.dedent("""
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
    """)
    locals = {}
    exec(code, None, locals)
    exc = locals['exc']
    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)


@pytest.mark.skipif(sys.version_info[:2] < (3, 3), reason='>=py3.3 only')
def test_get_root_exception_mixed():

    # have to exec this so we don't break pytest collection under py2
    code = textwrap.dedent("""
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
    """)
    locals = {}
    exec(code, None, locals)
    exc = locals['exc']
    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_errno_fields_permissions():
    exc = None
    try:
        open('/blah', 'w')
    except Exception as e:
        exc = e

    assert talisker.util.get_errno_fields(exc) == {
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

    assert talisker.util.get_errno_fields(exc) == {
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

    assert talisker.util.get_errno_fields(exc) == {
        'errno': 'EAI_NONAME',
        'strerror': 'Name or service not known',
    }
