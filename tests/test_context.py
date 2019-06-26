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

import sys
import threading

import future.utils
import pytest

from talisker.context import (
    Context,
    ContextStack,
    enable_gevent_context,
    enable_eventlet_context,
)


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

    def worker():
        Context.logging.push(a=2)
        Context.track('test', 1.0)
        e1.set()
        e2.wait()
        assert Context.logging.flat == {'a': 2}
        Context.logging.pop()
        e1.set()
        assert Context.logging.flat == {}
        assert Context.current.tracking['test'].count == 1

    t = threading.Thread(target=worker)

    Context.track('test', 1.0)
    Context.logging.push(a=1)
    assert Context.logging.flat == {'a': 1}

    t.start()
    e1.wait()
    e1.clear()

    assert Context.logging.flat == {'a': 1}
    assert Context.current.tracking['test'].count == 1

    e2.set()
    e1.wait()

    assert Context.logging.flat == {'a': 1}
    t.join()


@pytest.mark.skipif(sys.version_info >= (3, 7), reason="<py3.7 only")
def test_context_gevent(request):
    try:
        import gevent
    except ImportError:
        pytest.skip('gevent must be installed')

    request.addfinalizer(enable_gevent_context())

    def f1():
        assert Context.logging.flat == {}
        Context.logging.push({'f1': 1})
        Context.track('gevent', 1.0)
        assert Context.logging.flat == {'f1': 1}
        assert Context.current.tracking['gevent'].count == 1
        gevent.sleep(0.2)  # yield to let f2 run
        assert Context.logging.flat == {'f1': 1}
        assert Context.current.tracking['gevent'].count == 1

    def f2():
        assert Context.logging.flat == {}
        Context.logging.push({'f2': 2})
        Context.track('gevent', 1.0)
        assert Context.current.tracking['gevent'].count == 1
        assert Context.logging.flat == {'f2': 2}

    g1 = gevent.spawn(f1)
    g2 = gevent.spawn(f2)
    gevent.joinall([g1, g2], timeout=2)


@pytest.mark.skipif(sys.version_info >= (3, 7), reason="<py3.7 only")
def test_context_eventlet(request):
    try:
        import eventlet
    except ImportError:
        pytest.skip('eventlet must be installed')

    request.addfinalizer(enable_eventlet_context())

    def f1():
        assert Context.logging.flat == {}
        Context.logging.push({'f1': 1})
        Context.track('gevent', 1.0)
        assert Context.logging.flat == {'f1': 1}
        assert Context.current.tracking['gevent'].count == 1
        eventlet.sleep(0.2)  # yield to let f2 run
        assert Context.logging.flat == {'f1': 1}
        assert Context.current.tracking['gevent'].count == 1

    def f2():
        assert Context.logging.flat == {}
        Context.logging.push({'f2': 2})
        Context.track('gevent', 1.0)
        assert Context.current.tracking['gevent'].count == 1
        assert Context.logging.flat == {'f2': 2}

    pool = eventlet.GreenPool()
    pool.spawn(f1)
    pool.spawn(f2)
    pool.waitall()


if future.utils.PY3:
    from tests.py3_asyncio_context import test_context_asyncio  # NOQA


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
