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

# ignore this whole file for flake8, as when run underpy2 it will break
# flake8: noqa

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import talisker.util


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
    root = talisker.util.get_root_exception(exc)
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
    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)
