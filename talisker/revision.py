#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
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
    return os.environ.get('TALISKER_REVISION_ID').encode('utf-8')


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
