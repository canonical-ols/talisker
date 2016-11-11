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

import functools
import os
import logging

from werkzeug.local import Local
from talisker import logs, request_id
from talisker import statsd



__all__ = [
    'logging',
    'delay',
    'enable_metrics',
    ]

_local = Local()
_local.timers = {}


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


#celery signals for metrics


def _counter(name):
    def signal(sender, **kwargs):
        stat_name = 'celery.{}.{}'.format(sender.name, name)
        statsd.get_client().incr(stat_name)
    return signal


task_retry = _counter('retry')
task_success = _counter('success')
task_failure = _counter('failure')
task_revoked = _counter('revoked')


def get_id(body, headers):
    """get the task id, supporting both celery 4.0.x and 3.1.x"""
    id = None
    if 'id' in headers:
        id = headers['id']
    elif 'id' in body:
        id = body['id']
    return id


def before_task_publish(sender, body, headers={}, **kwargs):
    # TODO: find a way to avoid thread locals
    if not hasattr(_local, 'timers'):
        _local.timers = {}
    name = 'celery.{}.enqueue'.format(sender)
    timer = statsd.get_client().timer(name)
    id = get_id(body, headers)
    if id is not None:
        _local.timers[id] = timer
        timer.start()


def after_task_publish(sender, body, headers={}, **kwargs):
    id = get_id(body, headers)
    if id is not None:
        timer = _local.timers.pop(id)
        if timer:
            timer.stop()


def task_prerun(sender, task_id, task, **kwargs):
    name = 'celery.{}.run'.format(sender.name)
    task.__talisker_timer = statsd.get_client().timer(name)
    task.__talisker_timer.start()


def task_postrun(sender, task_id, task, **kwargs):
    task.__talisker_timer.stop()


def enable_metrics():
    """Best effort enabling of celery metrics"""
    try:
        from celery import signals
    except ImportError:  # pragma: no cover
        return

    # these should only be fired on the clients
    signals.before_task_publish.connect(before_task_publish)
    signals.after_task_publish.connect(after_task_publish)

    # these should only be fired on the workers
    signals.task_prerun.connect(task_prerun)
    signals.task_postrun.connect(task_postrun)
    signals.task_retry.connect(task_retry)
    signals.task_success.connect(task_success)
    signals.task_failure.connect(task_failure)
    signals.task_revoked.connect(task_revoked)

    logging.getLogger(__name__).info('enabled celery task statsd metrics')


def main():
    # these must be done before importing celery.
    logs.configure()
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = 'False'
    os.environ['CELERYD_REDIRECT_STDOUTS'] = 'False'

    import celery
    if celery.__version__ < '3.1.0':
        raise Exception('talisker does not support celery < 3.1.0')

    from celery.__main__ import main
    from celery.signals import setup_logging

    # take control of this signal, which prevents celery from setting up it's
    # own logging
    @setup_logging.connect
    def setup_celery_logging(**kwargs):
        # TODO: maybe add process id to extra?
        pass  # pragma: no cover

    enable_metrics()
    main()
