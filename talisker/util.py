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
__metaclass__ = type

import errno
import functools
import logging
import os
import pkg_resources
import sys
import threading
import time

import werkzeug.local
from future.moves.urllib.parse import urlparse
import future.utils


# look up table for errno's
# FIXME: maybe add more codes?
ERROR_CODES = errno.errorcode.copy()
ERROR_CODES[-1] = 'EAI_BADFLAGS'
ERROR_CODES[-2] = 'EAI_NONAME'
ERROR_CODES[-3] = 'EAI_AGAIN'
ERROR_CODES[-4] = 'EAI_FAIL'
ERROR_CODES[-5] = 'EAI_NODATA'
ERROR_CODES[-6] = 'EAI_FAMILY'
ERROR_CODES[-7] = 'EAI_SOCKTYPE'
ERROR_CODES[-8] = 'EAI_SERVICE'
ERROR_CODES[-9] = 'EAI_ADDRFAMILY'
ERROR_CODES[-10] = 'EAI_MEMORY'
ERROR_CODES[-11] = 'EAI_SYSTEM'
ERROR_CODES[-12] = 'EAI_OVERFLOW'


EARLY_LOGS = []
EARLY_LOGS_PROCESSED = False


def early_log(name, level, *args, **kwargs):
    """Logger wrap for talisker startup code.

    Collects logs for later processing when logging is initialised
    """
    if EARLY_LOGS_PROCESSED:
        logger = logging.getLogger(name)
        getattr(logger, level)(*args, **kwargs)
    else:
        EARLY_LOGS.append((name, level, args, kwargs))


def flush_early_logs():
    global EARLY_LOGS, EARLY_LOGS_PROCESSED
    EARLY_LOGS_PROCESSED = True

    # process pending logs
    for name, level, args, kwargs in EARLY_LOGS:
        early_log(name, level, *args, **kwargs)
    EARLY_LOGS[:] = []


def parse_url(url, proto='http'):
    # urlparse won't parse properly without a protocol
    if '://' not in url:
        url = proto + '://' + url
    return urlparse(url)


CLEANED = '{scheme}://{user}{colon}{password}{at}{hostname}{port}{path}{qs}'


def sanitize_url(url):
    """Strips a url of any pw and query strings."""
    parsed = parse_url(url)
    return CLEANED.format(
        scheme=parsed.scheme,
        user=parsed.username or '',
        colon=':' if parsed.password else '',
        password='********' if parsed.password else '',
        at='@' if parsed.username or parsed.password else '',
        hostname=parsed.hostname,
        port=':' + str(parsed.port) if parsed.port else '',
        path=parsed.path,
        qs='?' if parsed.query else '',
    )


def force_unicode(s):
    if isinstance(s, bytes):
        return s.decode('utf8')
    return s


def set_wsgi_header(headers, name, value):
    """Replace a wsgi header, ensuring correct encoding"""
    native_name = future.utils.text_to_native_str(name)
    for i, (k, v) in enumerate(headers):
        if native_name == k:
            headers[i] = (native_name, future.utils.text_to_native_str(value))
            return

    headers.append((native_name, future.utils.text_to_native_str(value)))


def get_rounded_ms(start_time, now_time=None):
    if now_time is None:
        now_time = time.time()
    ms = (now_time - start_time) * 1000
    return round(ms, 3)


def pkg_is_installed(name):
    try:
        return pkg_resources.get_distribution(name)
    except pkg_resources.DistributionNotFound:
        return False


def pkg_version(name):
    return pkg_resources.get_distribution(name).version


class TaliskerVersionException(Exception):
    pass


def ensure_extra_versions_supported(extra):
    # as this is an optional aid, don't fail if on old version of pip
    try:
        talisker_pkg = pkg_resources.get_distribution('talisker')
        extra_deps = (
            set(talisker_pkg.requires([extra])) - set(talisker_pkg.requires())
        )
        for requirement in extra_deps:
            pkg = pkg_resources.get_distribution(requirement.project_name)
            if pkg.version not in requirement.specifier:
                raise TaliskerVersionException(
                    '{} {} is not supported ({})'.format(
                        requirement.project_name, pkg.version, requirement))
    except Exception:
        logging.getLogger(__name__).debug(
            'skipping ensure_extra_versions_supported as exception occured')

    return True


# module level caches for global objects, means we can store all globals in
# a single place. This is useful when testing, as we can reset globals easily.
_global_cache = {}
_global_dicts = []
_context_locals = []


def module_cache(func):
    """Decorates a function to cache its result in a module dict."""

    # Maybe use id(func) instead? Strings are more debug friendly, though.
    id = func.__module__ + '.' + func.__name__

    @functools.wraps(func)
    def get(*args, **kwargs):
        """Return the object from cache, or create it"""
        if id not in _global_cache:
            _global_cache[id] = func(*args, **kwargs)
        return _global_cache[id]

    @functools.wraps(func)
    def update(*args, **kwargs):
        """Force update of the cached object"""
        _global_cache[id] = func(*args, **kwargs)
        return _global_cache[id]

    def raw_update(item):
        """Set the object in the cache directly"""
        old = _global_cache.get(id, None)
        _global_cache[id] = item
        return old

    # expose the raw function, useful for testing
    get.uncached = func
    get.update = update
    get.raw_update = raw_update

    return get


def module_dict():
    d = {}
    _global_dicts.append(d)
    return d


def clear_globals():
    _global_cache.clear()
    for d in _global_dicts:
        d.clear()


def clear_context_locals():
    for local in _context_locals:
        werkzeug.local.release_local(local)


if sys.version_info[0:2] >= (3, 3):
    def get_root_exception(exc):
        root = exc
        while root.__cause__ is not None or root.__context__ is not None:
            if root.__cause__ is not None:
                root = root.__cause__
            elif root.__context__ is not None:
                root = root.__context__
        return root

else:
    def get_root_exception(exc):
        return exc


def get_errno_fields(exc):
    """Best effort attempt to get any POSIX errno codes from exception."""
    root = get_root_exception(exc)
    fields = {}
    # these fields are standard fields in the OSError heirarchy
    if getattr(root, 'errno', None):
        fields['errno'] = ERROR_CODES.get(root.errno, str(root.errno))
    if getattr(root, 'strerror', None):
        fields['strerror'] = root.strerror
    if getattr(root, 'filename', None) is not None:
        fields['filename'] = root.filename
    if getattr(root, 'filename2', None) is not None:
        fields['filename2'] = root.filename2
    return fields


if future.utils.PY3:
    def datetime_to_timestamp(dt):
        return dt.timestamp()
else:
    def datetime_to_timestamp(dt):
        time.mktime(dt.utctimetuple())


class Local(object):
    """Wrap a threading.local that will be cleared on fork."""
    def __init__(self):
        self._local = threading.local()
        self._local._pid = os.getpid()

    def _check(self):
        pid = os.getpid()
        if self._local._pid != pid:
            self._local = threading.local()
            self._local._pid = pid

    # proxy through to _local
    def __getattr__(self, item):
        self._check()
        return getattr(self._local, item)

    def __setattr__(self, item, value):
        if item == '_local':
            super(Local, self).__setattr__(item, value)
        else:
            self._check()
            setattr(self._local, item, value)
