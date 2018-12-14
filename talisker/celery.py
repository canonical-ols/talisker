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
import time

import talisker
import talisker.logs
import talisker.metrics
import talisker.request_id
from talisker.sentry import ProxyClientMixin, get_log_handler
from talisker.util import module_cache


__all__ = [
    'enable_signals',
]


class CeleryMetric:

    count = talisker.metrics.Counter(
        name='celery_count',
        documentation='Count of all celery jobs',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    success = talisker.metrics.Counter(
        name='celery_success',
        documentation='Count of celery successful jobs',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    failure = talisker.metrics.Counter(
        name='celery_failure',
        documentation='Count of celery failed jobs',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    retry = talisker.metrics.Counter(
        name='celery_retry',
        documentation='Count of celery retried jobs',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    revoked = talisker.metrics.Counter(
        name='celery_revoke',
        documentation='Count of celery revoked jobs',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    latency = talisker.metrics.Histogram(
        name='celery_latency_run',
        documentation='Latency of celery jobs run time',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    enqueue_latency = talisker.metrics.Histogram(
        name='celery_latency_enqueue',
        documentation='Latency of celery jobs queue time',
        labelnames=['job'],
        statsd='{name}.{job}',
    )

    queue_latency = talisker.metrics.Histogram(
        name='celery_latency_queue',
        documentation='Latency of celery jobs wait in the queue',
        labelnames=['job'],
        statsd='{name}.{job}',
    )


def _counter(metric):
    """Create a signal handler that counts metrics"""
    def signal(sender, **kwargs):
        metric.inc(job=sender.name)
    return signal


def _protected_counter(metric):
    """Count metrics, but ensure only once.

    This is needed when tasks are eagerly invoked and have retries, or else
    metrics will be duplicated."""
    attr = '_talisker_sent_' + str(metric)

    def protected_signal(sender, **kwargs):
        if not hasattr(sender, attr):
            metric.inc(job=sender.name)
            setattr(sender, attr, True)
    return protected_signal


task_retry = _counter(CeleryMetric.retry)
task_success = _protected_counter(CeleryMetric.success)
task_failure = _protected_counter(CeleryMetric.failure)
task_revoked = _protected_counter(CeleryMetric.revoked)


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
    CeleryMetric.count.inc(job=sender)


def after_task_publish(sender, body, **kwargs):
    start_time = get_store(body, kwargs.get('headers', {})).get(ENQUEUE_START)
    if start_time is not None:
        ms = (time.time() - start_time) * 1000
        CeleryMetric.enqueue_latency.observe(ms, job=sender)


def send_run_metric(name, ts):
    ms = (time.time() - ts) * 1000
    CeleryMetric.latency.observe(ms, job=name)


def task_prerun(sender, task_id, task, **kwargs):
    rid = get_header(task.request, REQUEST_ID)
    if rid is not None:
        talisker.request_id.push(rid)

    start_time = get_header(task.request, ENQUEUE_START)
    if start_time is not None:
        ms = (time.time() - start_time) * 1000
        CeleryMetric.queue_latency.observe(ms, job=sender.name)

    if hasattr(task, 'talisker_timestamp') and task.request.is_eager:
        # eager task, but retry has happened immeadiately, so send metrics
        send_run_metric(sender.name, task.talisker_timestamp)
        task_retry(sender)

    task.talisker_timestamp = time.time()
    talisker.logs.logging_context.push(task_id=task_id, task_name=task.name)


def task_postrun(sender, task_id, task, **kwargs):
    if hasattr(task, 'talisker_timestamp'):
        send_run_metric(sender.name, task.talisker_timestamp)
        del task.talisker_timestamp
    talisker.context.clear()


@module_cache
def get_sentry_handler():
    # Need to defer this import so importing talisker.celery doesn't require
    # celery. This is cached, so usually we're only creating one class.
    from raven.contrib.celery import SentryCeleryHandler

    class TaliskerSentryCeleryHandler(ProxyClientMixin, SentryCeleryHandler):
        pass

    return TaliskerSentryCeleryHandler(None)


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
    # de-dup celery errors
    log_handler = get_log_handler()
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
