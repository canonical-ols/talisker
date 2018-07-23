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


def test_talisker_revision_id(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    monkeypatch.setenv('TALISKER_REVISION_ID', '7')
    rev = revision.get.uncached()
    assert rev == '7'


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
