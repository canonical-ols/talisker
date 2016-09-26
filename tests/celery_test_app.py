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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import logging
import os
import celery
import talisker.celery


broker_dir = '.broker'
in_dir = os.path.join(broker_dir, 'in')
out_dir = os.path.join(broker_dir, 'out')
processed_dir = os.path.join(broker_dir, 'processed')

mkdir = lambda p: os.path.exists(p) or os.makedirs(p)

def setup():
    mkdir(in_dir)
    mkdir(out_dir)
    mkdir(processed_dir)
    app = celery.Celery('tests.celery_test_app', broker='redis://localhost:6379')
    #app.conf.BROKER_TRANSPORT_OPTIONS = {
    #    "data_folder_in": in_dir,
    #    "data_folder_out": out_dir,
    #    "data_folder_processed": processed_dir,
    #}
    return app

app = setup()

@app.task
@talisker.celery.log
def job(i):
    logger = logging.getLogger(__name__)
    logger.info('hi', extra={'foo': i})


if __name__ == '__main__':
    talisker.celery.enable_metrics()
    logging.info('starting')
    for i in range(1000):
        print(i)
        job.delay(i)
