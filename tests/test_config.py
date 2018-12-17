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
import sys
from subprocess import check_output as run
import textwrap

import pytest

from talisker import config


@pytest.fixture
def raw():
    return config.Config.DEFAULTS.copy()


def assert_config(env, **expected):
    raw = config.load_env_config(env)
    cfg = config.Config(raw)
    for k, v in expected.items():
        value = getattr(cfg, k)
        assert value == v, "'{}' config is '{}' not '{}'".format(k, value, v)

    config.CONFIG_CACHE.clear()
    return cfg


def test_config_defaults():
    assert_config(
        {},
        devel=False,
        debuglog=None,
        colour=False,
        slowquery_threshold=-1,
        soft_request_timeout=-1,
        logstatus=False,
        networks=[],
    )


def test_config_colour(monkeypatch):
    assert_config({'TALISKER_COLOUR': '1'}, devel=False, colour=False)
    assert_config(
        {'DEVEL': '1', 'TERM': 'dumb'},
        devel=True,
        colour=False,
    )
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOUR': '0'},
        devel=True,
        colour=False,
    )
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOUR': '1'},
        devel=True,
        colour='default',
    )
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOR': '1'},
        devel=True,
        colour='default',
    )
    assert_config(
        {'DEVEL': '1', 'TALISKER_COLOUR': 'simple'},
        devel=True,
        colour='simple',
    )
    cfg = assert_config(
        {'DEVEL': '1', 'TALISKER_COLOUR': 'garbage'},
        devel=True,
        colour=False,
    )
    err_msg = str(cfg.ERRORS['TALISKER_COLOUR'])
    assert err_msg == 'garbage is not a valid colour scheme'
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert_config({'DEVEL': '1'}, devel=True, colour='default')


def test_logstatus_config():
    assert_config({'TALISKER_LOGSTATUS': '1'}, logstatus=True)
    assert_config({'TALISKER_LOGSTATUS': 'garbage'}, logstatus=False)


def test_debuglog_config():
    assert_config({'DEBUGLOG': '/tmp/log'}, debuglog='/tmp/log')
    assert_config({'DEBUGLOG': 1}, debuglog='1')


def test_query_threshold_config():
    assert_config(
        {'TALISKER_SLOWQUERY_THRESHOLD': '3000'}, slowquery_threshold=3000)
    cfg = assert_config(
        {'TALISKER_SLOWQUERY_THRESHOLD': 'garbage'}, slowquery_threshold=-1)
    msg = str(cfg.ERRORS['TALISKER_SLOWQUERY_THRESHOLD'])
    assert msg == "'garbage' is not a valid integer"


def test_request_timeout_config():
    assert_config(
        {'TALISKER_SOFT_REQUEST_TIMEOUT': '3000'}, soft_request_timeout=3000)
    cfg = assert_config(
        {'TALISKER_SOFT_REQUEST_TIMEOUT': 'garbage'}, soft_request_timeout=-1)
    msg = str(cfg.ERRORS['TALISKER_SOFT_REQUEST_TIMEOUT'])
    assert msg == "'garbage' is not a valid integer"


def test_load_env_config_filters():
    raw = config.load_env_config({
        'DEVEL': '1',
        'UNKNOWN': 'foo',
    })
    assert raw == {'DEVEL': '1'}


def test_load_env_config_file(tmpdir, monkeypatch):
    pyconfig = textwrap.dedent("""
        DEVEL = False
        DEBUGLOG = '/path'
    """).strip()
    path = tmpdir.join('config.py')
    path.write(pyconfig)
    env = {
        'DEVEL': '1',
        'TALISKER_CONFIG': str(path),
    }
    raw = config.load_env_config(env)
    assert raw == {
        'DEVEL': '1',
        'DEBUGLOG': '/path',
        'TALISKER_CONFIG': str(path),
    }


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


requires_bzr = pytest.mark.skipif(
    not is_bzr_configured(),
    reason='bzr not installed/configured')

requires_git = pytest.mark.skipif(
    not is_git_configured(),
    reason='git not installed/configured')


@requires_git
def test_git(tmpdir):
    tmpdir.chdir()
    run(['git', 'init', '.'])
    run(['git', 'config', 'user.email', 'someone@email.com'])
    run(['git', 'config', 'user.name', 'someone'])
    run(['touch', 'foo'])
    run(['git', 'add', 'foo'])
    run(['git', 'commit', '-m', 'init'])
    rev = config.get_revision_id()
    assert len(rev) == 40


def set_up_bzr():
    run(['bzr', 'init', '.'])
    run(['bzr', 'whoami', 'someone@email.com', '--branch'])
    run(['touch', 'foo'])
    run(['bzr', 'add', 'foo'])
    run(['bzr', 'commit', '-m', 'init'])


@requires_bzr
def test_bzr(tmpdir):
    tmpdir.chdir()
    set_up_bzr()
    rev = config.get_revision_id()
    assert rev == '1'


@requires_bzr
@pytest.mark.skipif(sys.version_info >= (3, 0), reason="requires python2")
def test_bzr_version_info_py2(monkeypatch, tmpdir):
    tmpdir.chdir()
    monkeypatch.syspath_prepend(str(tmpdir))
    set_up_bzr()
    vinfo = run(['bzr', 'version-info', '--format=python'])
    with open('versioninfo.py', 'wb') as f:
        f.write(vinfo)
    rev = config.get_revision_id()
    assert rev == '1'


def test_version_info(tmpdir):
    tmpdir.chdir()
    with open('version-info.txt', 'wb') as f:
        f.write(b'1\n')
    rev = config.get_revision_id()
    assert rev == '1'


def test_setup_py(tmpdir, capsys):
    setup_py = textwrap.dedent("""
    from distutils.core import setup
    setup(version='VERSION')
    """)
    tmpdir.chdir()
    with open('setup.py', 'w') as f:
        f.write(setup_py)
    rev = config.get_revision_id()
    assert rev == 'VERSION'
    out, err = capsys.readouterr()
    assert err == ''
