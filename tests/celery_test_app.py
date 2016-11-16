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
import talisker.celery


app = celery.Celery('tests.celery_test_app', broker='redis://localhost:6379')
logger = logging.getLogger(__name__)


@app.task(bind=True)
@talisker.celery.log
def job_a(self):
    logger.info('job a')


@app.task(bind=True)
@talisker.celery.log
def job_b(self):
    logger.info('job b')
    try:
        raise Exception('failed task')
    except Exception:
        self.retry(countdown=1, max_retries=3)


if __name__ == '__main__':
    talisker.celery.enable_metrics()
    logging.info('starting')
    job_a.delay()
    job_b.delay()
    job = job_b.delay()
    job.revoke()
