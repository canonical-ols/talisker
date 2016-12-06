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

import pip
from builtins import *  # noqa

import functools

from future.moves.urllib.parse import urlparse


def parse_url(url, proto='http'):
    # urlparse won't parse properly without a protocol
    if not url.startswith(proto + '://'):
        url = proto + '://' + url
    return urlparse(url)


def pkg_is_installed(name):
    return name in [x.project_name for x in pip.get_installed_distributions()]


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
