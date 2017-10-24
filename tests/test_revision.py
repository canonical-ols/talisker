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

from subprocess import check_output as run
import sys
import tempfile
import textwrap

from talisker import revision
from pytest import mark


def is_git_configured():
    try:
        git = run(['which', 'git']).strip()
    except Exception:
        return False
    return git != ""


def is_bzr_configured():
    try:
        bzr = run(['which', 'bzr']).strip()
    except Exception:
        return False
    return bzr != ""


requires_bzr = mark.skipif(
    not is_bzr_configured(),
    reason='bzr not installed/configured')

requires_git = mark.skipif(
    not is_git_configured(),
    reason='git not installed/configured')


@requires_git
def test_git(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    run(['git', 'init', '.'])
    run(['git', 'config', 'user.email', 'someone@email.com'])
    run(['git', 'config', 'user.name', 'someone'])
    run(['touch', 'foo'])
    run(['git', 'add', 'foo'])
    run(['git', 'commit', '-m', 'init'])
    rev = revision.get.uncached()
    assert len(rev) == 40


def set_up_bzr():
    run(['bzr', 'init', '.'])
    run(['bzr', 'whoami', 'someone@email.com', '--branch'])
    run(['touch', 'foo'])
    run(['bzr', 'add', 'foo'])
    run(['bzr', 'commit', '-m', 'init'])


@requires_bzr
def test_bzr(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    set_up_bzr()
    rev = revision.get.uncached()
    assert rev == '1'


@requires_bzr
@mark.skipif(sys.version_info >= (3, 0), reason="requires python2")
def test_bzr_version_info_py2(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    monkeypatch.syspath_prepend(dir)
    set_up_bzr()
    vinfo = run(['bzr', 'version-info', '--format=python'])
    with open('versioninfo.py', 'wb') as f:
        f.write(vinfo)
    rev = revision.get.uncached()
    assert rev == '1'


def test_version_info(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    with open('version-info.txt', 'wb') as f:
        f.write(b'1\n')
    rev = revision.get.uncached()
    assert rev == '1'


def test_setup_py(monkeypatch, capsys):
    setup_py = textwrap.dedent("""
    from distutils.core import setup
    setup(version='VERSION')
    """)
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    with open('setup.py', 'w') as f:
        f.write(setup_py)
    rev = revision.get.uncached()
    assert rev == 'VERSION'
    out, err = capsys.readouterr()
    assert err == ''
