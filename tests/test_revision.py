#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

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
