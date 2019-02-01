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


# example

from talisker.network import retry


@retry(exceptions.SomeException, endpoints=['a', 'b', 'c'])
def call_service(method, path, endpoint):
    session = talisker.get_session()
    return session.request(method, urljoin(endpoint + path))


ctx = retry_context(excpetions, endpoints=endpoints)


with retry(exceptions, endpoints) as endpoint:
    session.get(urljoin(endpoint, '/foo'))


with load_balance(endpoints, exceptions=exceptions) as endpoint:
    resp = session.get(urljoin(endpoint, '/foo'))


retry = talisker.requests.retry_context(
    endpoints=endpoints,
    retry_exceptions=[],
    retry_status_codes=[],
)


svc = talisker.requests.Service(
    servers=servers
    retry_exceptions=[],
    retry_status_codes=[],
)

return svc.get('/foo')


