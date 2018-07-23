##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

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
