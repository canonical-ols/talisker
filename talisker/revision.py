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
    return subprocess.check_output([sys.executable, 'setup.py', '--version'])


revision_funcs = [
    version_info_txt,
    git,
    bzr,
    bzr_version_info,
    hg,
    setup_py,
]


def load_revision():
    for func in revision_funcs:
        try:
            rev = func()
            if rev:
                return rev.strip().decode('utf8')
        except:
            pass
    return u'unknown'


def get():
    global revision
    if revision is None:
        revision = load_revision()
    return revision


def set(custom_revision):
    global revision, http_safe_revision
    revision = custom_revision
    http_safe_revision = None


def header():
    global http_safe_revision
    if http_safe_revision is None:
        http_safe_revision = get().strip().replace('\n', '\\n')
    return http_safe_revision
