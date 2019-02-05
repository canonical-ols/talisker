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

from py.test import fixture

from talisker import request_id


@fixture
def id():
    return request_id.generate()


def test_decorator(id):

    @request_id.decorator(lambda: id)
    def test():
        assert request_id.get() == id

    assert request_id.get() is None
    test()
    assert request_id.get() is None


def test_context(id):
    assert request_id.get() is None
    with request_id.context(id):
        assert request_id.get() == id
    assert request_id.get() is None


def test_context_existing_id(id):
    request_id.push('existing')
    assert request_id.get() == 'existing'
    with request_id.context(id):
        assert request_id.get() == id
    assert request_id.get() == 'existing'


def test_push():
    assert request_id.get() is None
    request_id.push(None)
    assert request_id.get() is None
    request_id.push('id')
    assert request_id.get() == 'id'
    request_id.push(None)
    assert request_id.get() is None
