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

import functools
import logging
import subprocess
import os

import celery

import talisker.celery
from talisker import request_id

def test_logging(log):

    app = celery.Celery()
    app.conf.update(CELERY_ALWAYS_EAGER=True)
    logger = logging.getLogger(__name__)

    @app.task
    @talisker.celery.logging
    def foo(a):
        logger.info('test')

    with request_id.context('id'):
        talisker.celery.delay(foo, 1).get()
    tags = log[0]._structured
    assert tags['request_id'] == 'id'
    assert len(tags['task_id']) == 36  # uuid


def test_celery_entrypoint():
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker.celery'
    subprocess.check_output([entrypoint, 'inspect', '--help'])
