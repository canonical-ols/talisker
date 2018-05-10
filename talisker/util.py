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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import errno
import functools
import logging
import pkg_resources
import sys

from future.moves.urllib.parse import urlparse


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


def pkg_is_installed(name):
    try:
        return pkg_resources.get_distribution(name)
    except pkg_resources.DistributionNotFound:
        return False


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
        _global_cache[id] = item

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
