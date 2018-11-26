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

from werkzeug.local import release_local
from talisker.util import context_local

# a per request/job context. Generally, this will be the equivalent of thread
# local storage, but if greenlets are being used it will be a greenlet local.
CONTEXT = context_local()


def clear():
    release_local(CONTEXT)


class ContextStack(Mapping):
    """A stacked set of dicts stored in a context.

    Support lookups and iteration, which go from top of the stack down.
    Can also be used as a context manager.

    """
    def __init__(self, name, *dicts):
        """Initialise stack, with name to use in context storage."""
        self._name = name
        self._stack.extend(dicts)

    def __eq__(self, other):
        return (
            self._name == other._name
            and list(self) == list(other)
        )

    def _clear(self):
        storage = {'stack': [], 'flattened': None}
        setattr(CONTEXT, self._name, storage)
        return storage

    def clear(self):
        """Clear the stack."""
        self._clear()

    @property
    def _storage(self):
        storage = getattr(CONTEXT, self._name, None)
        if storage is None:
            storage = self._clear()
        return storage

    @property
    def _stack(self):
        return self._storage['stack']

    @property
    def flat(self):
        """Cached flattened dict"""
        _flat = self._storage.get('flattened', None)
        if _flat is None:
            _flat = self._storage['flattened'] = OrderedDict(self._iterate())
        return _flat

    def _clear_flat(self):
        self._storage['flattened'] = None

    def _iterate(self):
        """Iterate from top to bottom, preserving individual dict ordering."""
        seen = set()
        for d in reversed(self._stack):
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
        level = len(self._stack)
        self._stack.append(d)
        self._clear_flat()
        return level

    def pop(self):
        """Pop the most recent dict from the stack"""
        if self._stack:
            self._stack.pop()
        self._clear_flat()

    def unwind(self, level):
        """Unwind the stack to a specific level."""
        while len(self._stack) > level:
            self._stack.pop()
        self._clear_flat()

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


class Tracker():
    def __init__(self):
        self.count = 0
        self.time = 0.0


def track_request_metric(type, duration):
    tracking = getattr(CONTEXT, 'request_tracking', defaultdict(Tracker))
    tracking[type].count += 1
    tracking[type].time += duration
    CONTEXT.request_tracking = tracking
