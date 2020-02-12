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
from future.utils import text_to_native_str
from ipaddress import ip_network, ip_address
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
CONFIG_META = collections.OrderedDict()
CONFIG_ALIASES = {
    'TALISKER_COLOUR': 'TALISKER_COLOR',
}
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


def force_int(n):
    try:
        return int(n)
    except ValueError:
        raise Exception("'{}' is not a valid integer".format(n))


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
        'TALISKER_COLOUR': False,
        'TALISKER_LOGSTATUS': False,
        'TALISKER_SLOWQUERY_THRESHOLD': -1,
        'TALISKER_SOFT_REQUEST_TIMEOUT': -1,
        'TALISKER_NETWORKS': [],
        'TALISKER_ID_HEADER': 'X-Request-Id',
        'TALISKER_DEADLINE_HEADER': 'X-Request-Deadline',
        'TALISKER_EXPLAIN_SQL': False,
    }

    Metadata = collections.namedtuple(
        'Metadata',
        ['name', 'value', 'raw', 'default', 'doc', 'error']
    )

    METADATA = CONFIG_META
    ERRORS = CONFIG_ERRORS
    SANITISE_URLS = {'SENTRY_DSN'}
    DEFAULT_SANITISE_KEYS = {'sessionid', 'csrftoken'}

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
        meta = collections.OrderedDict()
        for raw_name, (attr, doc) in self.METADATA.items():
            value = getattr(self, attr)
            if value:
                if raw_name in self.SANITISE_URLS:
                    value = sanitize_url(value)
                elif isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
            meta[raw_name] = self.Metadata(
                raw_name,
                value,
                self.raw.get(raw_name),
                self.DEFAULTS.get(raw_name),
                doc,
                CONFIG_ERRORS.get(raw_name),
            )
        return meta

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

    @config_property('TALISKER_CONFIG')
    def config_file(self, raw_name):
        """A path to a python file containing configuration variables.

        Note: this will only have effect when set via environment variable, for
        obvious reasons.
        """
        return self[raw_name]

    @config_property('DEVEL')
    def devel(self, raw_name):
        """Allows coloured logs, warnings, and other development convieniences.

        DEVEL mode enables coloured log output, enables python warnings and,
        for gunicorn, it sets longer timeouts and auto reloads by default.
        """
        return self.is_active(raw_name)

    @config_property('TALISKER_COLOUR')
    def colour(self, raw_name):
        """Controls the coloured output of logs. Defaults to on if stdin
        is a tty. Can be set to: 0 (off), 1 (on), or 'simple' for a simpler
        colourscheme. Requires DEVEL mode to be enabled.

        Can also be disabled with TERM=dumb env var.
        """

        # explicit disable
        if not self.devel:
            return False
        if os.environ.get('TERM', '').lower() == 'dumb':
            return False

        # was it explicitly set
        if raw_name in self.raw:
            colour = self.raw.get(raw_name).lower()
            if colour in self.ACTIVE:
                return 'default'
            elif colour in self.INACTIVE:
                return False
            else:
                if colour not in ['default', 'simple']:
                    raise Exception(
                        '{} is not a valid colour scheme'.format(colour)
                    )
                return colour
        else:
            # default behaviour when devel=True
            return 'default' if sys.stderr.isatty() else False

    @config_property('DEBUGLOG')
    def debuglog(self, raw_name):
        """Path to write debug level logs to, which is enabled if path is
        writable.

        Debug logs are rotated every 24h to limit size, with only a single
        24 hour archive is kept.
        """
        log = self[raw_name]
        if log is None:
            return None
        else:
            return str(log)

    @config_property('TALISKER_SLOWQUERY_THRESHOLD')
    def slowquery_threshold(self, raw_name):
        """Set the threshold (in ms) over which SQL queries will be logged.
        Defaults to -1 (off). The queries are sanitised, and thus safe to ship
        to a log aggregator.

        Setting to 0 will log every query, which can be useful in development.
        The queries are sanitized by not including the bind parameter values.
        """
        return force_int(self[raw_name])

    @config_property('TALISKER_EXPLAIN_SQL')
    def explain_sql(self, raw_name):
        """Include EXPLAIN plans in sql sentry breadcrumbs. Defaults to false.

        When enabled, this will issue extra queries to the db when generating
        sentry reports. The EXPLAIN queries will be quick to execute, as it
        doesn't actually run the query, but still, caution is advised.
        """
        return self.is_active(raw_name)

    @config_property('TALISKER_SOFT_REQUEST_TIMEOUT')
    def soft_request_timeout(self, raw_name):
        """Set the threshold (in ms) over which WSGI requests will report a
        soft time out to sentry. Defaults to -1 (off).

        A soft timeout is simply a warning-level sentry report for the request.
        The aim is to provide early warning and context for when things exceed
        some limit.

        Note: this can be set on a per-endpoint basis using the
        `talisker.request_timeout` decorator.
        """
        return force_int(self[raw_name])

    @config_property('TALISKER_REQUEST_TIMEOUT')
    def request_timeout(self, raw_name):
        """Set a deadline for all requests. Any network requests that talisker
        suports (requests, psycopg2) will have their timeouts set to this
        deadline.

        Note: this can be set on a per-endpoint basis using the
        `talisker.request_timeout` decorator.
        """
        value = self[raw_name]
        if value is None:
            return None
        return force_int(value)

    @config_property('TALISKER_LOGSTATUS')
    def logstatus(self, raw_name):
        """Sets whether http requests to /_status/ endpoints are logged in
        the access log or not.  Defaults to false.

        These log lines can add a lot of noise, so they are turned off by
        default."""
        return self.is_active(raw_name)

    @config_property('TALISKER_NETWORKS')
    def networks(self, raw_name):
        """Sets additional CIDR networks that are allowed to access restricted
        /_status/ endpoints. Comma separated list.

        This protection is very basic, and can be easily spoofed by
        X-Forwarded-For headers. You should ensure that your HTTP front end
        server is configuring these correctly before passing on to gunicorn.
        """
        network_tokens = self.raw.get(raw_name, '').split()
        networks = [ip_network(force_unicode(n)) for n in network_tokens]
        return networks

    @config_property('TALISKER_STATUS_INTERFACE')
    def status_interface(self, raw_name):
        """Which network interface to respond to /_status requests on."""
        return self[raw_name]

    @config_property('TALISKER_REVISION_ID')
    def revision_id(self, raw_name):
        """Sets the explicit revision of the application. If not set, a best
        effort detection of VCS revision is used.

        This is used to tag sentry reports, as well as returned as a header and
        from /_status/ping.

        The default lookup will try find a version-info.txt file, or git, hg,
        or bzr revno, and finally a setup.py version."""
        if raw_name in self.raw:
            return self.raw[raw_name]
        return get_revision_id()

    @config_property('TALISKER_UNIT')
    def unit(self, raw_name):
        """Sets the instance name for use with sentry reports."""
        return self[raw_name]

    @config_property('TALISKER_ENV')
    def environment(self, raw_name):
        """Sets the deployed environment for use with sentry reports (e.g.
        production, staging).
        """
        return self[raw_name]

    @config_property('TALISKER_DOMAIN')
    def domain(self, raw_name):
        """Sets the site domain name for use with sentry reports."""
        return self[raw_name]

    @config_property('STATSD_DSN')
    def statsd_dsn(self, raw_name):
        """Sets the Statsd DSN string, in the form: udp://host:port/my.prefix

        You can also add the querystring parameter ?maxudpsize=N, to change
        from the default of 512.
        """
        return self[raw_name]

    @config_property('SENTRY_DSN')
    def sentry_dsn(self, raw_name):
        """Sets the sentry DSN, as per usual sentry client configuration.

        See the sentry DSN documentation for more details."""
        return self[raw_name]

    @config_property('TALISKER_SANITISE_KEYS')
    def sanitise_keys(self, raw_name):
        """Comma separated list of keys with sensitive information. Data in
        these keys is masked in logging and sentry reports.

        Note that sentry's default set of password keys are already included
        - this is for extra keys.
        """
        tokens = self.raw.get(raw_name, '').split(',')
        return set(s for s in tokens if s.strip())

    @config_property('TALISKER_ID_HEADER')
    def id_header(self, raw_name):
        """Header containing request id. Defaults to X-Request-Id."""
        return text_to_native_str(self[raw_name])

    @config_property('TALISKER_DEADLINE_HEADER')
    def deadline_header(self, raw_name):
        """Header for request deadline. Defaults to X-Request-Deadline."""
        return text_to_native_str(self[raw_name])

    @property
    def wsgi_id_header(self):
        return 'HTTP_' + self.id_header.upper().replace('-', '_')

    def is_trusted_addr(self, addr_str):
        if not addr_str:
            return False
        ip = ip_address(force_unicode(addr_str))
        return ip.is_loopback or any(
            ip in network for network in self.networks
        )


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

    # process aliases
    for name, alias in CONFIG_ALIASES.items():
        if name not in env and alias in env:
            env[name] = env.pop(alias)

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
