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

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
__metaclass__ = type

import os
import subprocess
import sys

from past.builtins import execfile

from talisker.util import module_cache, module_dict


__all__ = ['get_config']


CONFIG_CACHE = module_dict()


class cached_property(object):
    """A property that caches it value in a global dict, so can be cleared."""
    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func
        self.key = func.__name__

    def __get__(self, obj, cls):
        if obj is None:
            return self

        if self.key not in CONFIG_CACHE:
            CONFIG_CACHE[self.key] = self.func(obj)

        return CONFIG_CACHE[self.key]


@module_cache
def get_config(env=os.environ):
    raw = get_raw_config(env)
    return Config(raw)


class Config():
    ACTIVE = set(['true', '1', 'yes', 'on'])
    INACTIVE = set(['false', '0', 'no', 'off'])
    DEFAULTS = {
        # development
        'DEVEL': False,
        'DEBUGLOG': None,
        'TALISKER_COLOR': False,
        # production
        'STATSD_DSN': None,
        'SENTRY_DSN': None,
        # 'TALISKER_DOMAIN': None,
        # 'TALISKER_ENV': None,
        # 'TALISKER_UNIT': None,
        'TALISKER_LOGSTATUS': False,
        'TALISKER_NETWORKS': None,
        'TALISKER_SLOWQUERY_THRESHOLD': -1,
        'TALISKER_SOFT_REQUEST_TIMEOUT': -1,
        'TALISKER_REVISION_ID': None,
    }

    def __init__(self, raw):
        self.raw = raw

    def __getitem__(self, name):
        return self.raw.get(name, self.DEFAULTS[name])

    def __setitem__(self, name, value):
        """Testing helper"""
        assert name in self.DEFAULTS
        CONFIG_CACHE.pop(name, None)
        self.raw[name] = value

    def is_active(self, name):
        value = self[name]
        if isinstance(value, str):
            return value.lower() in self.ACTIVE
        else:
            return value

    def is_not_active(self, name):
        value = self[name]
        if isinstance(value, str):
            return value.lower() in self.INACTIVE
        else:
            return value

    @cached_property
    def devel(self):
        return self.is_active('DEVEL')

    @cached_property
    def color(self):
        # explicit disable
        if not self.devel:
            return False
        if os.environ.get('TERM', '').lower() == 'dumb':
            return False

        # was it explicitly set
        if 'TALISKER_COLOR' in self.raw:
            color = self.raw.get('TALISKER_COLOR').lower()
            if color in self.ACTIVE:
                return 'default'
            elif color in self.INACTIVE:
                return False
            else:
                return color
        else:
            # default behaviour when devel=True
            return 'default' if sys.stderr.isatty() else False

    @cached_property
    def debuglog(self):
        return self['DEBUGLOG']

    @cached_property
    def slowquery_threshold(self):
        return int(self['TALISKER_SLOWQUERY_THRESHOLD'])

    @cached_property
    def soft_request_timeout(self):
        return int(self['TALISKER_SOFT_REQUEST_TIMEOUT'])

    @cached_property
    def logstatus(self):
        return self.is_active('TALISKER_LOGSTATUS')

    @cached_property
    def statsd_dsn(self):
        return self['STATSD_DSN']

    @cached_property
    def sentry_dsn(self):
        return self['SENTRY_DSN']

    @cached_property
    def networks(self):
        return self['TALISKER_NETWORKS']

    @cached_property
    def revision_id(self):
        if 'TALISKER_REVISION_ID' in self.raw:
            return self.raw['TALISKER_REVISION_ID']
        return get_revision_id()


def parse_config_file(filename):
    module = {
        "__builtins__": __builtins__,
        "__name__": "__config__",
        "__file__": filename,
        "__doc__": None,
        "__package__": None
    }
    execfile(filename, module, module)
    return module


def get_raw_config(env=os.environ):
    """Load talisker config from environment"""

    raw_config = dict()
    file_cfg = {}
    path = env.get('TALISKER_CONFIG')

    if path:
        if os.path.exists(path):
            file_cfg = parse_config_file(path)
        else:
            raise RuntimeError('Config file {} does not exists'.format(path))

    for name in Config.DEFAULTS:
        value = env.get(name, file_cfg.get(name, None))
        if value is not None:
            raw_config[name] = value

    return raw_config


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


def get_revision_id():
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
