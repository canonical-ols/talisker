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
