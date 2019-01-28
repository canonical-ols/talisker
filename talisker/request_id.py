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

from contextlib import contextmanager
from functools import wraps
import uuid

from talisker.logs import logging_context


__all__ = [
    'get',
    'push',
    'context',
    'decorator',
]


def generate():
    return str(uuid.uuid4())


def get():
    return logging_context.get('request_id')


def push(id):
    return logging_context.push(request_id=id)


# b/w compat alias
set = push


# provide a nicer ctx manager api
@contextmanager
def context(id):
    with logging_context(request_id=id):
        yield


def decorator(id_func):
    """Decorator to set a thread local request id for function.

    Takes a function that will return the request id from the function params,
    so you can configure it. Cleans up on the way out.
    """
    def wrapper(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            id = id_func(*args, **kwargs)

            if id:
                with context(id):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return decorator
    return wrapper
