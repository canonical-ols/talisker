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
import os
import subprocess
import pytest


SCRIPT = """
import logging
logging.getLogger('test').info('test', extra={'foo': 'bar'})
"""


@pytest.fixture
def script(tmpdir):
    py_script = tmpdir.join('test.py')
    py_script.write(SCRIPT)
    return str(py_script)


def test_run_entrypoint(script):
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker.run'
    output = subprocess.check_output(
        [entrypoint, script],
        stderr=subprocess.STDOUT,
    )
    lines = [l for l in output.decode('utf8').split('\n') if l]
    assert 'test' in lines[-1]
    assert 'foo=bar' in lines[-1]


def test_module_entrypoint(script):
    entrypoint = os.environ['VENV_BIN'] + '/' + 'python'
    output = subprocess.check_output(
        [entrypoint, '-m', 'talisker', script],
        stderr=subprocess.STDOUT,
    )
    lines = [l for l in output.decode('utf8').split('\n') if l]
    assert 'test' in lines[-1]
    assert 'foo=bar' in lines[-1]
