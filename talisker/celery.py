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
import os

from talisker import logs, request_id


__all__ = [
    'logging',
    'delay',
    ]


def log(func):
    """Add celery specific logging context."""
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        from celery import current_task
        tags = {'task_id': current_task.request.id}
        if 'request_id' in kwargs:
            tags['request_id'] = kwargs.pop('request_id')
        with logs.extra_logging(extra=tags):
            return func(*args, **kwargs)

    return decorator


def delay(task, *args, **kwargs):
    id = request_id.get()
    if id:
        kwargs['request_id'] = id
    return task.delay(*args, **kwargs)


def run():
    # these must be done before importing celery.
    logs.configure()
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = 'False'

    from celery.__main__ import main
    from celery.signals import setup_logging

    # take control of this signal, which prevents celery from setting up it's
    # own logging
    @setup_logging.connect
    def setup_celery_logging(**kwargs):
        # TODO: maybe add process id to extra?
        pass

    main()
