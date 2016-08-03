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

from subprocess import check_output as run
import sys
import tempfile

from talisker import revision
import pytest


def test_git(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    run(['git', 'init', '.'])
    run(['touch', 'foo'])
    run(['git', 'add', 'foo'])
    run(['git', 'commit', '-m', 'init'])
    rev = revision.git()
    assert len(rev.strip()) == 40


def set_up_bzr():
    run(['bzr', 'init', '.'])
    run(['touch', 'foo'])
    run(['bzr', 'add', 'foo'])
    run(['bzr', 'commit', '-m', 'init'])


def test_bzr(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    set_up_bzr()
    rev = revision.bzr()
    assert rev.strip() == b'1'


@pytest.mark.skipif(sys.version_info >= (3, 0), reason="requires python2")
def test_bzr_version_info_py2(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    monkeypatch.syspath_prepend(dir)
    set_up_bzr()
    vinfo = run(['bzr', 'version-info', '--format=python'])
    with open('versioninfo.py', 'wb') as f:
        f.write(vinfo)
    rev = revision.bzr_version_info()
    assert rev.strip() == '1'
