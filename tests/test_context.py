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

import uuid
import threading
import pytest
from talisker.context import ContextStack, clear


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


def test_context_clear_resets_stack(name):
    stack = ContextStack(name)
    stack.push(a=1)
    assert stack._stack == [{'a': 1}]
    assert stack.flat == {'a': 1}

    clear()

    assert stack._stack == []
    assert stack.flat == {}


def test_concurrent(name):
    stack = ContextStack(name)

    result = []

    e1 = threading.Event()
    e2 = threading.Event()

    def worker():
        stack.push(a=2)
        result.append(stack.flat)
        e1.set()
        e2.wait()
        stack.clear()
        result.append(stack.flat)
        e1.set()

    t = threading.Thread(target=worker)

    stack.push(a=1)
    t.start()

    e1.wait()
    e1.clear()

    # we should now have 2 different thread locals
    assert stack.flat == {'a': 1}
    assert result[-1] == {'a': 2}

    e2.set()
    e1.wait()

    assert stack.flat == {'a': 1}
    assert result[-1] == {}

    t.join()
