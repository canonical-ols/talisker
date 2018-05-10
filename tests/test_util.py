
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
