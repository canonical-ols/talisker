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

import sys
import os
import logging
import time

import talisker
import talisker.logs
import talisker.request_id
import talisker.statsd
from talisker.util import module_cache, ensure_extra_versions_supported


__all__ = [
    'enable_signals',
]


def _counter(name):
    """Create a signal handler that counts metrics"""
    def signal(sender, **kwargs):
        stat_name = 'celery.{}.{}'.format(sender.name, name)
        talisker.statsd.get_client().incr(stat_name)
    return signal


task_retry = _counter('retry')
task_success = _counter('success')
task_failure = _counter('failure')
task_revoked = _counter('revoked')


REQUEST_ID = 'talisker_request_id'
ENQUEUE_START = 'talisker_enqueue_start'


def get_store(body, headers):
    """celery 3.1/4.0 compatability shim."""
    if isinstance(body, tuple):  # celery 4.0.x
        return headers
    else:  # celery 3.1.x
        return body


def get_header(request, header):
    attr = getattr(request, header, None)
    if attr is not None:
        return attr
    if request.headers:
        return request.headers.get(header)
    return None


def before_task_publish(sender, body, headers, **kwargs):
    get_store(body, headers)[ENQUEUE_START] = time.time()
    rid = talisker.request_id.get()
    if rid is not None:
        headers[REQUEST_ID] = rid


def after_task_publish(sender, body, **kwargs):
    start_time = get_store(body, kwargs.get('headers', {})).get(ENQUEUE_START)
    if start_time is not None:
        ms = (time.time() - start_time) * 1000
        name = 'celery.{}.enqueue'.format(sender)
        talisker.statsd.get_client().timing(name, ms)


def task_prerun(sender, task_id, task, **kwargs):
    name = 'celery.{}.run'.format(sender.name)
    task.talisker_timer = talisker.statsd.get_client().timer(name)
    task.talisker_timer.start()
    rid = get_header(task.request, REQUEST_ID)
    if rid is not None:
        talisker.request_id.push(rid)
    talisker.logs.logging_context.push(task_id=task_id, task_name=task.name)


def task_postrun(sender, task_id, task, **kwargs):
    task.talisker_timer.stop()
    talisker.context.clear()


@module_cache
def get_sentry_handler():
    from raven.contrib.celery import SentryCeleryHandler
    client = talisker.sentry.get_client()
    signal_handler = SentryCeleryHandler(client)
    return signal_handler


def sentry_handler_update(client):
    get_sentry_handler().client = client


# By connecting our own no-op handler, we disable celery's logging
# all together
def celery_logging_handler(**kwargs):
    pass  # pragma: no cover


def enable_signals():
    """Best effort enabling of metrics, logging, sentry signals for celery."""
    try:
        from celery import signals
        from raven.contrib.celery import CeleryFilter
    except ImportError:  # pragma: no cover
        return

    signals.setup_logging.connect(celery_logging_handler)
    signals.before_task_publish.connect(before_task_publish)
    signals.after_task_publish.connect(after_task_publish)
    signals.task_prerun.connect(task_prerun)
    signals.task_postrun.connect(task_postrun)
    signals.task_retry.connect(task_retry)
    signals.task_success.connect(task_success)
    signals.task_failure.connect(task_failure)
    signals.task_revoked.connect(task_revoked)

    # install celery error handler
    get_sentry_handler().install()
    talisker.sentry.register_client_update(sentry_handler_update)
    # de-dup celery errors
    log_handler = talisker.sentry.get_log_handler()
    for filter in log_handler.filters:
        if isinstance(filter, CeleryFilter):
            break
    else:
        log_handler.addFilter(CeleryFilter())

    logging.getLogger(__name__).info('enabled talisker celery signals')


def disable_signals():
    from celery import signals
    get_sentry_handler().uninstall()
    signals.setup_logging.disconnect(celery_logging_handler)
    signals.before_task_publish.disconnect(before_task_publish)
    signals.after_task_publish.disconnect(after_task_publish)
    signals.task_prerun.disconnect(task_prerun)
    signals.task_postrun.disconnect(task_postrun)
    signals.task_retry.disconnect(task_retry)
    signals.task_success.disconnect(task_success)
    signals.task_failure.disconnect(task_failure)
    signals.task_revoked.disconnect(task_revoked)


def main(argv=sys.argv):
    # these must be done before importing celery.
    talisker.initialise()
    os.environ['CELERYD_REDIRECT_STDOUTS'] = 'False'
    # techincally we don't need this, as we disable celery's logging
    # altogether, but it doesn't hurt
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = 'False'
    ensure_extra_versions_supported('celery')

    from celery.bin.celery import main as celery_main
    enable_signals()
    celery_main(argv)
