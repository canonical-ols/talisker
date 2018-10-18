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

from collections import defaultdict, OrderedDict
from contextlib import contextmanager
import functools
import logging
import json
import os
import tempfile
import time

from talisker import prometheus_lock
import talisker.statsd
from talisker.util import pkg_version, TaliskerVersionException


try:
    import prometheus_client
    from prometheus_client.multiprocess import (
        MultiProcessCollector,
        mark_process_dead,
    )
    prom_version = pkg_version('prometheus_client')
    if prom_version in ('0.4.0', '0.4.1'):
        raise TaliskerVersionException(
            'prometheus_client {} has a critical bug in multiprocess mode, '
            'and is not supported in Talisker. '
            'https://github.com/prometheus/client_python/issues/322'.format(
                prom_version,
            )
        )

except ImportError:
    prometheus_client = False

    def mark_process_dead(pid):
        pass

try:
    import statsd
except ImportError:
    statsd = False


logger = logging.getLogger(__name__)


class Metric():
    """Abstraction over prometheus and statsd metrics."""

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.statsd_template = None

        if statsd:
            self.statsd_template = kwargs.pop('statsd', None)

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
        if self.prometheus:
            if labels:
                self.prometheus.labels(**labels).inc(amount)
            else:
                self.prometheus.inc(amount)

        if self.statsd_template:
            client = talisker.statsd.get_client()
            name = self.get_statsd_name(labels)
            client.incr(name, amount)


histogram_archive = 'histogram_archive.db'
counter_archive = 'counter_archive.db'


def histogram_sorter(sample):
    # sort histogram samples in order of bucket size
    name, labels, _ = sample[:3]
    return name, float(labels.get('le', 0))


def _filter_exists(paths):
    exists = []
    for path in paths:
        if os.path.exists(path):
            exists.append(path)
    return exists


def prometheus_cleanup_worker(pid):
    """Aggregate dead worker's metrics into a single archive file."""
    mark_process_dead(pid)
    prom_dir = os.environ['prometheus_multiproc_dir']
    worker_files = [
        'histogram_{}.db'.format(pid),
        'counter_{}.db'.format(pid),
    ]
    paths = _filter_exists(os.path.join(prom_dir, f) for f in worker_files)

    # check at least one worker file exists
    if not paths:
        return

    histogram_path = os.path.join(prom_dir, histogram_archive)
    counter_path = os.path.join(prom_dir, counter_archive)
    archive_paths = _filter_exists([histogram_path, counter_path])

    collect_paths = paths + archive_paths
    collector = MultiProcessCollector(None)

    try:
        metrics = collector.merge(collect_paths, accumulate=False)
    except AttributeError:
        metrics = legacy_collect(collect_paths)

    tmp_histogram = tempfile.NamedTemporaryFile(delete=False)
    tmp_counter = tempfile.NamedTemporaryFile(delete=False)
    write_metrics(metrics, tmp_histogram.name, tmp_counter.name)

    # ensure reader does get partial state
    with prometheus_lock:
        os.rename(tmp_histogram.name, histogram_path)
        os.rename(tmp_counter.name, counter_path)

        for path in paths:
            os.unlink(path)


def legacy_collect(files):
    """This almost verbatim from MultiProcessCollector.collect(), pre 0.4.0

    The original collects all results in a format designed to be scraped. We
    instead need to collect limited results, in a format that can be written
    back to disk. To facilitate this, this version of collect() preserves label
    ordering, and does not aggregate the histograms.

    Specifically, it differs from the original:

    1. it takes its files as an argument, rather than hardcoding '*.db'
    2. it does not accumulate histograms
    3. it preserves label order, to facilitate being inserted back into an mmap
       file.

    It needs to be kept up to date with changes to prometheus_client as much as
    possible, or until changes are landed upstream to allow reuse of collect().
    """
    from prometheus_client import core
    metrics = {}
    for f in files:
        if not os.path.exists(f):
            continue
        # verbatim from here...
        parts = os.path.basename(f).split('_')
        typ = parts[0]
        d = core._MmapedDict(f, read_mode=True)
        for key, value in d.read_all_values():
            # Note: key format changed in 0.4+
            metric_name, name, labelnames, labelvalues = json.loads(key)

            metric = metrics.get(metric_name)
            if metric is None:
                metric = core.Metric(metric_name, 'Multiprocess metric', typ)
                metrics[metric_name] = metric

            if typ == 'gauge':
                pid = parts[2][:-3]
                metric._multiprocess_mode = parts[1]
                metric.add_sample(
                    name,
                    tuple(zip(labelnames, labelvalues)) + (('pid', pid), ),
                    value,
                )
            else:
                # The duplicates and labels are fixed in the next for.
                metric.add_sample(
                    name,
                    tuple(zip(labelnames, labelvalues)),
                    value,
                )
        d.close()

    for metric in metrics.values():
        samples = defaultdict(float)
        buckets = {}
        for name, labels, value in metric.samples:
            if metric.type == 'gauge':
                without_pid = tuple(l for l in labels if l[0] != 'pid')
                if metric._multiprocess_mode == 'min':
                    current = samples.setdefault((name, without_pid), value)
                    if value < current:
                        samples[(name, without_pid)] = value
                elif metric._multiprocess_mode == 'max':
                    current = samples.setdefault((name, without_pid), value)
                    if value > current:
                        samples[(name, without_pid)] = value
                elif metric._multiprocess_mode == 'livesum':
                    samples[(name, without_pid)] += value
                else:  # all/liveall
                    samples[(name, labels)] = value

            elif metric.type == 'histogram':
                bucket = tuple(float(l[1]) for l in labels if l[0] == 'le')
                if bucket:
                    # _bucket
                    without_le = tuple(l for l in labels if l[0] != 'le')
                    buckets.setdefault(without_le, {})
                    buckets[without_le].setdefault(bucket[0], 0.0)
                    buckets[without_le][bucket[0]] += value
                else:
                    # _sum/_count
                    samples[(name, labels)] += value

            else:
                # Counter and Summary.
                samples[(name, labels)] += value

        # end of verbatim copy
        # modified to remove accumulation
        if metric.type == 'histogram':
            for labels, values in buckets.items():
                for bucket, value in sorted(values.items()):
                    key = (
                        metric.name + '_bucket',
                        labels + (('le', core._floatToGoString(bucket)),),
                    )
                    samples[key] = value

        # Convert to correct sample format.
        metric.samples = [
            # OrderedDict used instead of dict
            (name, OrderedDict(labels), value)
            for (name, labels), value in samples.items()
        ]
    return metrics.values()


def write_metrics(metrics, histogram_file, counter_file):
    from prometheus_client.core import _MmapedDict
    try:
        from prometheus_client.core import _mmap_key
    except ImportError:
        # pre 0.4 key format
        def _mmap_key(metric_name, name, labelnames, labelvalues):
            return json.dumps(
                (metric_name, name, tuple(labels), tuple(labels.values()))
            )

    histograms = _MmapedDict(histogram_file)
    counters = _MmapedDict(counter_file)

    try:
        for metric in metrics:
            if metric.type == 'histogram':
                sink = histograms
            elif metric.type == 'counter':
                sink = counters

            for sample in metric.samples:
                # prometheus_client 0.4+ adds extra fields
                name, labels, value = sample[:3]
                key = _mmap_key(
                    metric.name,
                    name,
                    tuple(labels),
                    tuple(labels.values()),
                )
                sink.write_value(key, value)
    finally:
        histograms.close()
        counters.close()
