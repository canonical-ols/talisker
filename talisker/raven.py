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

from future.utils import with_metaclass

from builtins import *  # noqa

import logging
import os

import raven
import raven.middleware
import raven.handlers.logging
import raven.breadcrumbs

from talisker import revision
from talisker.util import module_cache

record_log_breadcrumb = raven.breadcrumbs._record_log_breadcrumb


__all__ = [
    'get_client'
    'record_log_breadcrumb',
]

_client = None

default_processors = set([
    'raven.processors.RemovePostDataProcessor',
    'raven.processors.SanitizePasswordsProcessor',
    'raven.processors.RemoveStackLocalsProcessor',
])


def ensure_talisker_config(kwargs):
    # ensure default processors
    processors = kwargs.get('processors')
    if not processors:
        processors = set([])
    kwargs['processors'] = list(default_processors | processors)

    # override it or it interferes with talisker logging
    if kwargs.get('install_logging_hook'):
        logging.getLogger(__name__).info(
            'ignoring install_logging_hook=True in sentry config '
            '- talisker manages this')
    kwargs['install_logging_hook'] = False

    kwargs.setdefault('release', revision.get())
    # don't hook libraries by default
    kwargs.setdefault('hook_libraries', [])

    # set from the environment
    kwargs.setdefault('environment', os.environ.get('TALISKER_ENV'))
    # if not set, will default to hostname
    kwargs.setdefault('name', os.environ.get('TALISKER_UNIT'))
    kwargs.setdefault('site', os.environ.get('TALISKER_DOMAIN'))


@module_cache
def get_raw_client(**kwargs):
    ensure_talisker_config(kwargs)
    return raven.Client(**kwargs)


set_client = get_raw_client.update


class ProxyClient(object):
    __slots__ = ["__weakref__"]

    # proxying (special cases)
    def __getattribute__(self, name):
        return getattr(get_raw_client(), name)

    def __delattr__(self, name):
        delattr(get_raw_client(), name)

    def __setattr__(self, name, value):
        setattr(get_raw_client(), name, value)

    def __nonzero__(self):
        return bool(get_raw_client())

    def __str__(self):
        return str(get_raw_client())

    def __repr__(self):
        return repr(get_raw_client())

    #
    # factories
    #
    _special_names = [
        '__abs__', '__add__', '__and__', '__call__', '__cmp__', '__coerce__',
        '__contains__', '__delitem__', '__delslice__', '__div__', '__divmod__',
        '__eq__', '__float__', '__floordiv__', '__ge__', '__getitem__',
        '__getslice__', '__gt__', '__hash__', '__hex__', '__iadd__',
        '__iand__', '__idiv__', '__idivmod__', '__ifloordiv__', '__ilshift__',
        '__imod__', '__imul__', '__int__', '__invert__', '__ior__', '__ipow__',
        '__irshift__', '__isub__', '__iter__', '__itruediv__', '__ixor__',
        '__le__', '__len__', '__long__', '__lshift__', '__lt__', '__mod__',
        '__mul__', '__ne__', '__neg__', '__oct__', '__or__', '__pos__',
        '__pow__', '__radd__', '__rand__', '__rdiv__', '__rdivmod__',
        '__reduce__', '__reduce_ex__', '__repr__', '__reversed__',
        '__rfloorfiv__', '__rlshift__', '__rmod__', '__rmul__', '__ror__',
        '__rpow__', '__rrshift__', '__rshift__', '__rsub__', '__rtruediv__',
        '__rxor__', '__setitem__', '__setslice__', '__sub__', '__truediv__',
        '__xor__', 'next',
    ]

    @classmethod
    def _create_class_proxy(cls, theclass):
        """creates a proxy for the given class"""

        def make_method(name):
            def method(self, *args, **kw):
                return getattr(get_raw_client(), name)(*args, **kw)
            return method

        namespace = {}
        for name in cls._special_names:
            if hasattr(theclass, name):
                namespace[name] = make_method(name)
        return type(
             "%s(%s)" % (cls.__name__, theclass.__name__), (cls,), namespace)

    def __new__(cls, *args, **kwargs):
        """
        creates an proxy instance. (*args, **kwargs) are
        passed to this class' __init__, so deriving classes can define an
        __init__ method of their own.
        note: _class_proxy_cache is unique per deriving class (each deriving
        class must hold its own cache)
        """
        obj = get_raw_client()
        try:
            cache = cls.__dict__["_class_proxy_cache"]
        except KeyError:
            cls._class_proxy_cache = cache = {}
        try:
            theclass = cache[obj.__class__]
        except KeyError:
            cache[obj.__class__] = theclass = cls._create_class_proxy(
                obj.__class__)
        ins = object.__new__(theclass)
        theclass.__init__(ins, obj, *args, **kwargs)
        return ins


def get_client():
    return ProxyClient()
