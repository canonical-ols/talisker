#
# Copyright (c) 2015-2021 Canonical, Ltd.
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

from contextlib import contextmanager
import functools
import logging
import os
import time

import talisker.statsd


try:
    import prometheus_client
except ImportError:
    prometheus_client = False

try:
    import statsd
except ImportError:
    statsd = False


logger = logging.getLogger(__name__)


class Metric():
    """Abstraction over prometheus and statsd metrics."""

    def __init__(self, name, *args, _only_workers_prometheus=False, **kwargs):
        self.name = name
        self.statsd_template = None
        # If true, do not emit prometheus metrics in the gunicorn arbiter.
        # They're not particularly useful there and cause deadlocks when it
        # handles signals (signal handler being invoked when prometheus client
        # is holding an internal lock in response to emitting different metric)
        # and during signal handling logs an error, causing an http request to
        # sentry to be tracked in prometheus.
        self._only_workers_prometheus = _only_workers_prometheus
        self._origin_pid = os.getpid()

        if statsd:
            self.statsd_template = kwargs.pop('statsd', None)

        if prometheus_client:
            self._prometheus_metric = self.get_type()(name, *args, **kwargs)
        else:
            self._prometheus_metric = None

    @property
    def prometheus(self):
        if self._only_workers_prometheus and os.getpid() == self._origin_pid:
            return None
        return self._prometheus_metric

    # prometheus_client does some odd things, if we define this as a class
    # variable it doesn't work
    @property
    def metric_type(self):
        return None

    def get_type(self):
        if prometheus_client:
            return self.metric_type
        return None

    def get_statsd_name(self, labels):
        name = self.name.replace('_', '.')
        if self.statsd_template:
            try:
                name = self.statsd_template.format(name=name, **labels)
            except Exception:
                pass
        return name


def protect(msg):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            try:
                f(*args, **kwargs)
            except Exception:
                logger.exception(msg)
        return wrapper
    return decorator


class Histogram(Metric):

    @property
    def metric_type(self):
        return prometheus_client.Histogram

    @protect("Failed to collect histogram metric")
    def observe(self, amount, **labels):
        prom_metric = self.prometheus
        if prom_metric:
            if labels:
                prom_metric.labels(**labels).observe(amount)
            else:
                prom_metric.observe(amount)

        if self.statsd_template:
            client = talisker.statsd.get_client()
            name = self.get_statsd_name(labels)
            client.timing(name, amount)

    @contextmanager
    def time(self):
        """Measure time in ms."""
        t = time.time()
        yield
        d = time.time() - t
        self.observe(d * 1000)


class Counter(Metric):

    @property
    def metric_type(self):
        return prometheus_client.Counter

    @protect("Failed to increment counter metric")
    def inc(self, amount=1, **labels):
        prom_metric = self.prometheus
        if prom_metric:
            if labels:
                prom_metric.labels(**labels).inc(amount)
            else:
                prom_metric.inc(amount)

        if self.statsd_template:
            client = talisker.statsd.get_client()
            name = self.get_statsd_name(labels)
            client.incr(name, amount)
