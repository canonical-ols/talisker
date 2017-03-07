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
import talisker


def test_get_config(monkeypatch):
    parse = talisker.get_config
    assert parse({}) == {'devel': False, 'debuglog': None}
    assert parse({'DEVEL': 1}) == {'devel': True, 'debuglog': None}
    assert parse({'DEBUGLOG': '/tmp/log'}) == {
        'devel': False,
        'debuglog': '/tmp/log'
    }
    assert parse({'DEVEL': 1, 'DEBUGLOG': '/tmp/log'}) == {
        'devel': True,
        'debuglog': '/tmp/log',
    }
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert parse({}) == {'devel': True, 'debuglog': None}
