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

import uuid
import pytest
from talisker.context import ContextStack


@pytest.fixture
def name():
    return 'test' + str(uuid.uuid4())


def test_stack_basic(name):
    stack = ContextStack(name)

    stack.push(a=1)
    assert stack['a'] == 1
    assert list(stack.items()) == [('a', 1)]

    stack.push(b=2)
    assert stack['b'] == 2
    assert list(stack.items()) == [('b', 2), ('a', 1)]

    stack.push(a=3)
    assert stack['a'] == 3
    assert list(stack.items()) == [('a', 3), ('b', 2)]

    stack.pop()
    assert stack['a'] == 1
    assert list(stack.items()) == [('b', 2), ('a', 1)]

    stack.pop()
    assert stack['a'] == 1
    assert list(stack.items()) == [('a', 1)]

    stack.pop()
    with pytest.raises(KeyError):
        stack['a']
    assert list(stack.items()) == []


def test_stack_clear(name):
    stack = ContextStack(name)

    stack.push(a=1)
    stack.push(b=2)
    stack.push(c=3)

    assert list(stack.items()) == [('c', 3), ('b', 2), ('a', 1)]

    stack.clear()

    assert list(stack.items()) == []


def test_stack_context(name):
    stack = ContextStack(name)

    stack.push(a=1)

    assert list(stack.items()) == [('a', 1)]

    with stack(b=2):
        assert list(stack.items()) == [('b', 2), ('a', 1)]

    assert list(stack.items()) == [('a', 1)]


def test_stack_dict_arg(name):
    stack = ContextStack(name)

    with stack({'a': 1}):
        assert list(stack.items()) == [('a', 1)]

    with stack({'a': 1}, b=2):
        # order not preserved, as kwargs
        assert dict(stack) == {'a': 1, 'b': 2}


def test_stack_unwind(name):
    stack = ContextStack(name)

    stack.push(a=1)
    assert stack['a'] == 1

    level = stack.push(a=2)
    assert stack['a'] == 2

    stack.push(a=3)
    stack.push(a=4)
    assert stack['a'] == 4

    stack.unwind(level)
    assert stack['a'] == 1


def test_does_not_use_or_modify_dict(name):
    stack = ContextStack(name)

    d = {'a': 1}
    stack.push(d, b=2)
    assert stack['a'] == 1
    assert stack['b'] == 2
    assert d == {'a': 1}

    d['a'] = 2
    assert stack['a'] == 1


def test_name_doesnt_clash(name):
    stack1 = ContextStack(name)
    stack2 = ContextStack(name + 'xxx')

    stack1.push(a=1)
    stack2.push(a=2)

    assert stack1['a'] == 1
    assert stack2['a'] == 2


def test_instance_tracking(name):
    assert len(ContextStack._instances) == 1
    s = ContextStack(name)
    assert len(ContextStack._instances) == 2
    del s
    assert len(ContextStack._instances) == 1


def test_clear_all(name):
    stack = ContextStack(name)
    stack2 = ContextStack(name + 'xxx')
    stack.push(a=1)
    assert stack.flat == {'a': 1}
    assert stack._flat == {'a': 1}
    stack2.push(a=2)
    assert stack2.flat == {'a': 2}
    assert stack2._flat == {'a': 2}

    ContextStack._clear_all()

    assert stack._flat is None
    assert stack2._flat is None
