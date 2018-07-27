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

import logging
import celery

app = celery.Celery(
    'tests.celery_app',
    broker='redis://localhost:6379',
    backend='redis://localhost:6379',
)
logger = logging.getLogger(__name__)


@app.task(bind=True)
def basic_task(self):
    logger.info('basic task')
    return 'basic'


@app.task(bind=True)
def error_task(self):
    logger.info('error task')
    try:
        raise Exception('failed task')
    except Exception:
        self.retry(countdown=1, max_retries=1)


if __name__ == '__main__':
    import talisker
    talisker.initialise()
    import talisker.celery
    talisker.celery.enable_signals()
    logger = logging.getLogger('tests.celery_app')
    logger.info('starting')
    basic_task.delay()
    logger.info('started job a')
    with talisker.request_id.context('a'):
        basic_task.delay()
    logger.info('started job a with id a')
    basic_task.delay()
    logger.info('started job a')
    with talisker.request_id.context('b'):
        error_task.delay()
    logger.info('started job b with id b')
    with talisker.request_id.context('c'):
        job = error_task.delay()
    logger.info('started job b with id c')
    job.revoke()
    logger.info('revoked job b')
    error_task.apply()
    logger.info('done')
