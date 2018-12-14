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

import collections
from ipaddress import ip_network
import os
import subprocess
import sys

from past.builtins import execfile

from talisker.util import (
    force_unicode,
    module_cache,
    module_dict,
    sanitize_url,
)


__all__ = ['get_config']


# All valid config
CONFIG_META = {}
# A cache of calculated config values
CONFIG_CACHE = module_dict()
# Collect any configuration errors
CONFIG_ERRORS = module_dict()


def clear():
    CONFIG_CACHE.clear()
    CONFIG_ERRORS.clear()


@module_cache
def get_config(env=os.environ):
    raw = load_env_config(env)
    return Config(raw)


def config_property(raw_name):
    """A special property for declarative configuration specification.

    It collects all the config metadata together, caches parsing logic, and
    provides some convienience when writing configuration logic functions.
    """
    def decorator(func):
        CONFIG_META[raw_name] = (func.__name__, func.__doc__)

        class _property():
            def __get__(self, obj, cls):
                if obj is None:
                    return self
                if raw_name not in CONFIG_CACHE:
                    try:
                        # Note: also passes in the supplied name of the raw
                        # config value, for DRY.
                        CONFIG_CACHE[raw_name] = func(obj, raw_name)
                    except Exception as e:
                        CONFIG_ERRORS[raw_name] = e
                        CONFIG_CACHE[raw_name] = cls.DEFAULTS.get(raw_name)

                return CONFIG_CACHE[raw_name]

        prop = _property()
        prop.__doc__ = func.__doc__
        return prop

    return decorator


class Config():
    """Talisker specific configuration object.

    It takes a 'raw' dict with the unparsed config values in from os.environ or
    file, as appropriate. It then provides python level attributes to access
    that config, which parse the raw values as appropriate.
    """
    ACTIVE = set(['true', '1', 'yes', 'on'])
    INACTIVE = set(['false', '0', 'no', 'off'])
    DEFAULTS = {
        'DEVEL': False,
        'TALISKER_COLOR': False,
        'TALISKER_LOGSTATUS': False,
        'TALISKER_SLOWQUERY_THRESHOLD': -1,
        'TALISKER_SOFT_REQUEST_TIMEOUT': -1,
        'TALISKER_NETWORKS': [],
    }

    Metadata = collections.namedtuple(
        'Metadata',
        ['name', 'value', 'raw', 'default', 'doc', 'error']
    )

    METADATA = CONFIG_META
    ERRORS = CONFIG_ERRORS
    SANITIZE_URLS = {'SENTRY_DSN'}

    def __init__(self, raw):
        self.raw = raw

    def __getitem__(self, name):
        """Dict-like lookup of raw values."""
        return self.raw.get(name, self.DEFAULTS.get(name))

    def __setitem__(self, name, value):
        """Dict-like setting of raw values, used for testing"""
        CONFIG_CACHE.pop(name, None)
        self.raw[name] = value

    def metadata(self):
        for raw_name, (attr, doc) in CONFIG_META.items():
            value = getattr(self, attr)
            if value:
                if raw_name in self.SANITIZE_URLS:
                    value = sanitize_url(value)
                elif isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
            yield self.Metadata(
                raw_name,
                value,
                self.raw.get(raw_name),
                self.DEFAULTS.get(raw_name),
                doc,
                CONFIG_ERRORS.get(raw_name),
            )

    def is_active(self, name):
        """Is the named raw value truthy?"""
        value = self[name]
        if isinstance(value, str):
            return value.lower() in self.ACTIVE
        else:
            return value

    def is_not_active(self, name):
        """Is the named raw value falsey?"""
        value = self[name]
        if isinstance(value, str):
            return value.lower() in self.INACTIVE
        else:
            return value

    @config_property('DEVEL')
    def devel(self, raw_name):
        return self.is_active(raw_name)

    @config_property('TALISKER_COLOR')
    def color(self, raw_name):
        # explicit disable
        if not self.devel:
            return False
        if os.environ.get('TERM', '').lower() == 'dumb':
            return False

        # was it explicitly set
        if raw_name in self.raw:
            color = self.raw.get(raw_name).lower()
            if color in self.ACTIVE:
                return 'default'
            elif color in self.INACTIVE:
                return False
            else:
                if color not in ['default', 'simple']:
                    raise Exception(
                        '{} is not a valid color scheme'.format(color)
                    )
                return color
        else:
            # default behaviour when devel=True
            return 'default' if sys.stderr.isatty() else False

    @config_property('DEBUGLOG')
    def debuglog(self, raw_name):
        log = self[raw_name]
        if log is None:
            return None
        else:
            return str(log)

    @config_property('TALISKER_SLOWQUERY_THRESHOLD')
    def slowquery_threshold(self, raw_name):
        return int(self[raw_name])

    @config_property('TALISKER_SOFT_REQUEST_TIMEOUT')
    def soft_request_timeout(self, raw_name):
        return int(self[raw_name])

    @config_property('TALISKER_LOGSTATUS')
    def logstatus(self, raw_name):
        return self.is_active(raw_name)

    @config_property('STATSD_DSN')
    def statsd_dsn(self, raw_name):
        return self[raw_name]

    @config_property('SENTRY_DSN')
    def sentry_dsn(self, raw_name):
        return self[raw_name]

    @config_property('TALISKER_NETWORKS')
    def networks(self, raw_name):
        network_tokens = self.raw.get(raw_name, '').split()
        networks = [ip_network(force_unicode(n)) for n in network_tokens]
        return networks

    @config_property('TALISKER_REVISION_ID')
    def revision_id(self, raw_name):
        if raw_name in self.raw:
            return self.raw[raw_name]
        return get_revision_id()

    @config_property('TALISKER_UNIT')
    def unit(self, raw_name):
        return self[raw_name]

    @config_property('TALISKER_ENV')
    def environment(self, raw_name):
        return self[raw_name]

    @config_property('TALISKER_DOMAIN')
    def domain(self, raw_name):
        return self[raw_name]


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


def load_env_config(env=os.environ):
    """Load talisker config from environment"""

    raw_config = dict()
    file_cfg = {}
    path = env.get('TALISKER_CONFIG')

    if path:
        if os.path.exists(path):
            file_cfg = parse_config_file(path)
        else:
            raise RuntimeError('Config file {} does not exists'.format(path))

    for name in CONFIG_META:
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
