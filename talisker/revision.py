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

import subprocess
import sys

from talisker.util import module_cache

revision = None
http_safe_revision = None

__all__ = [
    'get',
    'set',
    'header',
]


def _run(args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def version_info_txt():
    with open('version-info.txt', 'rb') as f:
        return f.read()


def git():
    return _run(['git', 'rev-parse', 'HEAD'])


def bzr():
    return _run(['bzr', 'revno'])


def hg():
    return _run(['hg', 'id', '-i'])


def bzr_version_info():
    from versioninfo import version_info
    return version_info['revno']


def setup_py():
    return subprocess.check_output(
        [sys.executable, 'setup.py', '--version'], stderr=subprocess.STDOUT)


revision_funcs = [
    version_info_txt,
    git,
    bzr,
    bzr_version_info,
    hg,
    setup_py,
]


@module_cache
def get():
    for func in revision_funcs:
        try:
            rev = func()
            if rev:
                return rev.strip().decode('utf8')
        except Exception:
            pass
    return u'unknown'


@module_cache
def header():
    return get().strip().replace('\n', '\\n')


def set(custom_revision):
    get.raw_update(custom_revision)
    header.update()
