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

import os
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


def talisker_revision_id():
    return os.environ.get('TALISKER_REVISION_ID')


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
    talisker_revision_id,
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
                if hasattr(rev, "decode"):
                    return rev.strip().decode('utf8')
                else:
                    return rev.strip()
        except Exception:
            pass
    return u'unknown'


@module_cache
def header():
    return get().strip().replace('\n', '\\n')


def set(custom_revision):
    get.raw_update(custom_revision)
    header.update()
