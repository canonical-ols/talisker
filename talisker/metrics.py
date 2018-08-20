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

import functools
import logging
import json
import os
import shutil
import tempfile

import talisker.statsd


try:
    import prometheus_client
    from prometheus_client import multiprocess
except ImportError:
    prometheus_client = False

try:
    import statsd
except ImportError:
    statsd = False

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


class Metric():
    """Abstraction over prometheus and statsd metrics."""

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.statsd_template = kwargs.pop('statsd')

        if prometheus_client:
            self.prometheus = self.get_type()(name, *args, **kwargs)
        else:
            self.prometheus = None

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
        if self.prometheus:
            if labels:
                self.prometheus.labels(**labels).observe(amount)
            else:
                self.prometheus.observe(amount)

        if statsd:
            client = talisker.statsd.get_client()
            name = self.get_statsd_name(labels)
            client.timing(name, amount)


class Counter(Metric):

    @property
    def metric_type(self):
        return prometheus_client.Counter

    @protect("Failed to increment counter metric")
    def inc(self, amount=1, **labels):
        if self.prometheus:
            if labels:
                self.prometheus.labels(**labels).inc(amount)
            else:
                self.prometheus.inc(amount)

        if statsd:
            client = talisker.statsd.get_client()
            name = self.get_statsd_name(labels)
            client.incr(name, amount)


histogram_archive = 'histogram_archive.db'
counter_archive = 'counter_archive.db'


def prometheus_cleanup_worker(pid):
    """Clean up after a multiprocess worker has died."""
    if prometheus_client is None:
        return

    try:
        # just deletes delete gauge files
        multiprocess.mark_process_dead(pid)
        prom_dir = os.environ['prometheus_multiproc_dir']
        pid_files = [
            'histogram_{}.db'.format(pid),
            'counter_{}.db'.format(pid),
        ]
        paths = [os.path.join(prom_dir, f) for f in pid_files]

        # check at least one worker file exists
        if not any(os.path.exists(path) for path in paths):
            return

        metrics = collect_metrics(prom_dir, *pid_files)

        tmp_histogram = tempfile.NamedTemporaryFile(delete=False)
        tmp_counter = tempfile.NamedTemporaryFile(delete=False)
        write_metrics(metrics, tmp_histogram.name, tmp_counter.name)

        os.rename(
            tmp_histogram.name, os.path.join(prom_dir, histogram_archive))
        os.rename(
            tmp_counter.name, os.path.join(prom_dir, counter_archive))

        for path in paths:
            if os.path.exists(path):
                os.unlink(path)

    except Exception:
        # we should never fail at cleaning up
        logger.exception('failed to cleanup prometheus worker files')


def collect_metrics(prom_dir, *files):
    """Copy the files out of prom_dir into a separate dir, and collect them.

    This aggregates all the metrics together into one set.
    """
    from prometheus_client import CollectorRegistry

    all_files = [histogram_archive, counter_archive] + list(files)
    tmp = tempfile.mkdtemp(prefix='prometheus_aggregate')
    try:
        for filename in all_files:
            path = os.path.join(prom_dir, filename)
            if os.path.exists(path):
                shutil.copy(path, tmp)

        collector = multiprocess.MultiProcessCollector(CollectorRegistry())
        return collector.collect()
    finally:
        shutil.rmtree(tmp)


def write_metrics(metrics, histogram_file, counter_file):
    from prometheus_client.core import _MmapedDict
    histograms = _MmapedDict(histogram_file)
    counters = _MmapedDict(counter_file)

    for metric in metrics:
        if metric.type == 'histogram':
            sink = histograms
            metric.samples = unaccumulate(metric.samples)
        elif metric.type == 'counter':
            sink = counters

        for name, labels, value in metric.samples:
            key = json.dumps(
                (metric.name, name, tuple(labels), tuple(labels.values()))
            )
            sink.write_value(key, value)


def get_bucket(labels):
    if 'le' not in labels:
        return None, None
    le = labels['le']
    key = tuple((label, labels[label]) for label in labels if label != 'le')
    return float(le), key


def unaccumulate(samples):
    """Unaccumulate the histogram values that collect() accumulated."""
    buckets = {}

    # group the buckets by label
    for name, labels, value in samples:
        le, key = get_bucket(labels)
        if le:
            buckets.setdefault(key, {})
            assert le not in buckets[key]
            buckets[key][le] = value

    for labels, values in buckets.items():
        # subtract values to get original values
        bucket_keys = list(sorted(values))
        for i, bucket in reversed(list(enumerate(sorted(values)))):
            if i == 0:
                continue
            values[bucket] -= values[bucket_keys[i - 1]]

    for name, labels, value in samples:
        if name.endswith('_count'):
            continue  # relcalulated on collect
        elif name.endswith('_sum'):
            yield name, labels, value
        else:  # _bucket
            le, key = get_bucket(labels)
            if le != labels['le']:
                labels['le'] = le
            yield name, labels, buckets[key][le]
