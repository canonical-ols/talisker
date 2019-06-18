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

try:
    from collections.abc import Mapping
except ImportError:  # < py3.3
    from collections import Mapping

from collections import OrderedDict, defaultdict
from contextlib import contextmanager

try:
    from greenlet import getcurrent as get_context_id
except ImportError:
    try:
        from thread import get_ident as get_context_id
    except ImportError:
        from _thread import get_ident as get_context_id


__all__ = ['Context']


CONTEXTS = {}


class Tracker():
    def __init__(self):
        self.count = 0
        self.time = 0.0


class ContextData():
    """Talisker specific context data."""

    def __init__(self):
        self.request_id = None
        self.logging = ContextStack()
        self.tracking = defaultdict(Tracker)


class ContextAPI():
    """Global proxy to the current Talisker context."""

    @property
    def current(self):
        """Provide attribute proxy for current context instance."""
        return CONTEXTS.setdefault(get_context_id(), ContextData())

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

    def track(self, _type, duration):
        ctx = self.current
        ctx.tracking[_type].count += 1
        ctx.tracking[_type].time += duration

    def clear(self):
        CONTEXTS.pop(get_context_id(), None)


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
