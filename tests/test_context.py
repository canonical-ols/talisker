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

import threading
from greenlet import greenlet
import pytest
from talisker.context import CONTEXTS, get_context_id, Context, ContextStack


def test_context_api():
    Context.logging.push(a=1)
    Context.request_id = 'id'
    Context.track('test', 1.0)
    assert Context.current.logging.flat == {'a': 1}
    assert Context.current.request_id == 'id'
    assert Context.current.tracking['test'].count == 1
    assert Context.current.tracking['test'].time == 1.0

    Context.clear()
    assert Context.current.logging.flat == {}
    assert Context.current.request_id is None
    assert Context.current.tracking == {}


def test_context_thread():

    e1 = threading.Event()
    e2 = threading.Event()
    ids = []

    def worker():
        ids.append(get_context_id())
        Context.logging.push(a=2)
        e1.set()
        e2.wait()
        Context.logging.pop()
        e1.set()

    t = threading.Thread(target=worker)

    Context.logging.push(a=1)
    assert Context.logging.flat == {'a': 1}
    t.start()

    e1.wait()
    e1.clear()

    # we should now have 2 different thread locals
    print(CONTEXTS)
    assert len(CONTEXTS) == 2
    # this one is unchanged
    assert Context.logging.flat == {'a': 1}
    assert CONTEXTS[ids[0]].logging.flat == {'a': 2}

    e2.set()
    e1.wait()

    assert Context.logging.flat == {'a': 1}
    assert CONTEXTS[ids[0]].logging.flat == {}

    t.join()


def test_context_greenlet():

    ids = []

    def f1():
        ids.append(get_context_id())
        Context.logging.push(a=1)
        g2.switch()
        raise greenlet.GreenletExit()

    def f2():
        ids.append(get_context_id())
        Context.logging.push(a=2)
        g1.switch()

    g1 = greenlet(f1)
    g2 = greenlet(f2)
    g1.switch()

    assert len(CONTEXTS) == 2
    assert CONTEXTS[ids[0]].logging.flat == {'a': 1}
    assert CONTEXTS[ids[1]].logging.flat == {'a': 2}


def test_stack_basic():
    stack = ContextStack()

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


def test_stack_context_manager():
    stack = ContextStack()

    stack.push(a=1)

    assert list(stack.items()) == [('a', 1)]

    with stack(b=2):
        assert list(stack.items()) == [('b', 2), ('a', 1)]

    assert list(stack.items()) == [('a', 1)]


def test_stack_dict_arg():
    stack = ContextStack()

    with stack({'a': 1}):
        assert list(stack.items()) == [('a', 1)]

    with stack({'a': 1}, b=2):
        # order not preserved, as kwargs
        assert dict(stack) == {'a': 1, 'b': 2}


def test_stack_unwind():
    stack = ContextStack()

    stack.push(a=1)
    assert stack['a'] == 1

    level = stack.push(a=2)
    assert stack['a'] == 2

    stack.push(a=3)
    stack.push(a=4)
    assert stack['a'] == 4

    stack.unwind(level)
    assert stack['a'] == 1


def test_does_not_use_or_modify_dict():
    stack = ContextStack()

    d = {'a': 1}
    stack.push(d, b=2)
    assert stack['a'] == 1
    assert stack['b'] == 2
    assert d == {'a': 1}

    d['a'] = 2
    assert stack['a'] == 1


def test_tracking():
    Context.track('sql', 1.0)
    Context.track('sql', 2.0)
    Context.track('http', 3.0)

    assert Context.current.tracking['sql'].count == 2
    assert Context.current.tracking['sql'].time == 3.0
    assert Context.current.tracking['http'].count == 1
    assert Context.current.tracking['http'].time == 3.0
