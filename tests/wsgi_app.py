#
# Copyright (c) 2015-2021 Canonical, Ltd.
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

import pprint
import logging
import time


def application(environ, start_response):
    if environ['PATH_INFO'] == '/_status/check':
        status = '404 Not Found'
    else:
        status = '200 OK'
    start_response(status, [('content-type', 'text/plain')])
    output = pprint.pformat(environ)
    logger = logging.getLogger(__name__)
    logger.debug('debug')
    logger.info('info')
    logger.warning('warning')
    logger.error('error')
    logger.critical('critical')
    return [output.encode('utf8')]


def app404(environ, start_response):
    if environ['PATH_INFO'] == '/_status/ping':
        start_response('200 OK', [])
        return [b'OK']
    else:
        start_response('404 Not Found', [])
        return [b'Not Found']


def timeout(environ, start_response):
    time.sleep(1000)


def timeout2(environ, start_response):
    start_response('200 OK', [('content-type', 'text/plain')])
    time.sleep(1000)


def timeout3(environ, start_response):
    start_response('200 OK', [('content-type', 'text/plain')])

    def i():
        yield time.sleep(1000)

    return i()
