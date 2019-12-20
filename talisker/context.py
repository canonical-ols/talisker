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

import future.utils
try:
    from collections.abc import Mapping
except ImportError:  # py2
    from collections import Mapping

from collections import OrderedDict, defaultdict
from contextlib import contextmanager
import functools
import sys
import threading
import time
import uuid

from talisker.util import early_log, pkg_is_installed


__all__ = ['Context']


CONTEXT_MAP = {}  # global storage for contexts by id


if future.utils.PY3:
    import contextvars

    # enable asyncio aware contextvars in 3.5.3+/3.6
    if pkg_is_installed('aiocontextvars'):
        import asyncio
        # aiocontextvars only supports python 3.5.3+
        if hasattr(asyncio, '_get_running_loop'):
            import aiocontextvars  # NOQA
        else:
            early_log(
                __name__,
                'warning',
                'aiocontextvars is installed, but it does not function with '
                'python {}. Please use python >= 3.5.3 if you wish to use '
                'talisker with asyncio.'.format(
                    '.'.join(str(v) for v in sys.version_info[:3])
                )
            )

    ContextId = contextvars.ContextVar('talisker')
    CONTEXT_OBJ = contextvars
    CONTEXT_ATTR = '_state'
else:
    _NONE = object()

    class Python2ContextVar():
        """Tiny python2 implementation of ContextVar, enough for our purposes.

        It is not immutable, and it does not support the reset(token) API. But
        talisker only uses contextvars to store the current context id, so just
        set() and get() suffice.
        """
        local = threading.local()

        def get(self, default=_NONE):
            try:
                return self.local.value
            except AttributeError:
                if default is not _NONE:
                    return default

            raise LookupError

        def set(self, value):
            self.local.value = value

    ContextId = Python2ContextVar()
    CONTEXT_OBJ = Python2ContextVar
    CONTEXT_ATTR = 'local'


def setattr_undo(obj, attr, value):
    """Set attribute, returning a function to restore it."""
    old = getattr(obj, attr)
    setattr(obj, attr, value)

    def undo():
        setattr(obj, attr, old)

    return undo


def enable_gevent_context():
    if sys.version_info >= (3, 7):
        raise Exception('gevent can not work with contextvars in py3.7+')
    import gevent.local
    return setattr_undo(CONTEXT_OBJ, CONTEXT_ATTR, gevent.local.local())


def enable_eventlet_context():
    if sys.version_info >= (3, 7):
        raise Exception('eventlet can not work with contextvars in py3.7+')
    import eventlet.corolocal
    return setattr_undo(CONTEXT_OBJ, CONTEXT_ATTR, eventlet.corolocal.local())


class DeadlineExceeded(Exception):
    pass


class Tracker():
    def __init__(self):
        self.count = 0
        self.time = 0.0


class ContextData():
    """Talisker specific context data."""

    def __init__(self, context_id):
        self.id = context_id
        self.start_time = time.time()
        self.request_id = None
        self.logging = ContextStack()
        self.tracking = defaultdict(Tracker)
        self.soft_timeout = -1
        self.deadline = None
        self.debug = False

    def set_deadline(self, timeout):
        """Set the absolute request deadline."""
        self.deadline = self.start_time + (timeout / 1000)


def get_context(context_id):
    return CONTEXT_MAP[context_id]


def create_context(context_id=None):
    if context_id is None:
        context_id = str(uuid.uuid4())
    elif context_id in CONTEXT_MAP:
        return CONTEXT_MAP[context_id]

    ctx = ContextData(context_id)
    CONTEXT_MAP[context_id] = ctx
    return ctx


def delete_context(context_id):
    return CONTEXT_MAP.pop(context_id, None)


class ContextAPI():
    """Global proxy to the current Talisker context."""
    @property
    def current(self):
        """Provide attribute proxy for current context instance.

        Creates a new context if needed.
        """
        context_id = ContextId.get(None)
        if context_id is None:
            return self.new()

        return get_context(context_id)

    def clear(self):
        """Remove current context."""
        current_id = ContextId.get(None)
        if current_id is not None:
            delete_context(current_id)
            ContextId.set(None)

    def new(self):
        """Clear current context and explicitly create new one.

        This is to force the context creation timestamp to be at a particular
        point.
        """
        self.clear()
        ctx = create_context()
        ContextId.set(ctx.id)
        return ctx

    @property
    def logging(self):
        """Provide attribute proxy for current logging context."""
        return self.current.logging

    @property
    def request_id(self):
        return self.current.request_id

    @request_id.setter
    def request_id(self, _id):
        self.current.request_id = _id

    @property
    def debug(self):
        return self.current.debug

    def set_debug(self):
        self.current.debug = True

    def deadline_timeout(self):
        if self.current.deadline is None:
            return None

        timeout = self.current.deadline - time.time()
        if timeout <= 0:
            raise DeadlineExceeded()

        return timeout

    def track(self, _type, duration):
        ctx = self.current
        ctx.tracking[_type].count += 1
        ctx.tracking[_type].time += duration


Context = ContextAPI()


class ContextStack(Mapping):
    """A stacked set of dicts stored in a context.

    Support lookups and iteration, which go from top of the stack down.
    Can also be used as a context manager.

    """
    def __init__(self, *dicts):
        self.stack = list(dicts)
        self._flat = None

    def __eq__(self, other):
        return (
            self._name == other._name
            and list(self) == list(other)
        )

    @property
    def flat(self):
        """Cached flattened dict"""
        if self._flat is None:
            self._flat = OrderedDict(self._iterate())
        return self._flat

    def _iterate(self):
        """Iterate from top to bottom, preserving individual dict ordering."""
        seen = set()
        for d in reversed(self.stack):
            for k, v in d.items():
                if k not in seen:
                    yield k, v
            seen = seen.union(d)

    def push(self, _dict=None, **kwargs):
        """Add a new dict to the stack.

        Can take a single positional argument, which is a dict, and/or kwargs
        dict to use.

        Returns the stack level before adding this dict, for use with
        unwind."""
        if _dict is None:
            d = {}
        else:
            d = _dict.copy()
        d.update(kwargs)
        level = len(self.stack)
        self.stack.append(d)
        self._flat = None
        return level

    def pop(self):
        """Pop the most recent dict from the stack"""
        if self.stack:
            self.stack.pop()
        self._flat = None

    def unwind(self, level):
        """Unwind the stack to a specific level."""
        while len(self.stack) > level:
            self.stack.pop()
        self._flat = None

    @contextmanager
    def __call__(self, extra=None, **kwargs):
        """Context manager to push/run/pop."""
        self.push(extra, **kwargs)
        yield self
        self.pop()

    def __getitem__(self, item):
        """Key lookup, from top to bottom."""
        return self.flat[item]

    def __len__(self):
        return len(self.flat)

    def __iter__(self):
        """Iterate from top to bottom, preserving individual dict ordering."""
        return iter(self.flat)


class request_timeout():
    def __init__(self, timeout=None, soft_timeout=None):
        self.timeout = timeout
        self.soft_timeout = soft_timeout

    def __call__(self, f):

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if self.timeout:
                Context.current.set_deadline(self.timeout)
            if self.soft_timeout:
                Context.current.soft_timeout = self.soft_timeout

            return f(*args, **kwargs)

        return wrapper
