#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

try:
    from collections.abc import Mapping
except ImportError:  # < py3.3
    from collections import Mapping

from collections import OrderedDict
from contextlib import contextmanager

from werkzeug.local import Local, release_local

# a per request/job context. Generally, this will be the equivalent of thread
# local storage, but if greenlets are being used it will be a greenlet local.
context = Local()


def clear():
    release_local(context)


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
            self._name == other._name and
            list(self) == list(other)
        )

    def _clear(self):
        storage = {'stack': [], 'flattened': None}
        setattr(context, self._name, storage)
        return storage

    def clear(self):
        """Clear the stack."""
        self._clear()

    @property
    def _storage(self):
        storage = getattr(context, self._name, None)
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
