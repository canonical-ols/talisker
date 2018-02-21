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

try:
    from collections.abc import Mapping
except ImportError:  # < py3.3
    from collections import Mapping

from collections import OrderedDict
from contextlib import contextmanager

from werkzeug.local import Local, release_local
from werkzeug.wsgi import ClosingIterator

# a per request/job context. Generally, this will be the equivalent of thread
# local storage, but if greenlets are being used it will be a greenlet local.
context = Local()


def clear():
    release_local(context)


def wsgi_middleware(app):
    def middleware(environ, start_response):
        return ClosingIterator(app(environ, start_response), clear)
    return middleware


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
