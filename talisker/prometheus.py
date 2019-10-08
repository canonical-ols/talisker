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

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
from collections import defaultdict, OrderedDict
from contextlib import contextmanager
from multiprocessing import Lock
from pkg_resources import parse_version
import errno
import json
import logging
import os
import tempfile
import time

import talisker
from talisker.util import (
    early_log,
    pkg_is_installed,
    pkg_version,
    TaliskerVersionException)


prometheus_installed = pkg_is_installed('prometheus_client')
prometheus_version = parse_version(pkg_version('prometheus-client'))
if prometheus_installed and str(prometheus_version) in ('0.4.0', '0.4.1'):
    raise TaliskerVersionException(
        'prometheus_client {} has a critical bug in multiprocess mode, '
        'and is not supported in Talisker. '
        'https://github.com/prometheus/client_python/issues/322'.format(
            str(prometheus_version),
        )
    )


_lock = None
histogram_archive = 'histogram_archive.db'
counter_archive = 'counter_archive.db'


class PrometheusLockTimeout(Exception):
    pass


@contextmanager
def try_prometheus_lock_noop(timeout=10.0):
    """Default implementation: does nothing."""
    yield


try_prometheus_lock = try_prometheus_lock_noop


@contextmanager
def try_prometheus_lock_normal(timeout=10.0):
    """Try acquire the multiprocess lock, with timeout.

    Note: the timeout is implemented in C, so will block in async contexts.
    """
    if not _lock.acquire(timeout=timeout):
        raise PrometheusLockTimeout('Timeout acquiring prometheus lock')
    yield
    _lock.release()


@contextmanager
def try_prometheus_lock_patched_async(timeout=10.0):
    """Try acquire the multiprocss lock, with timeout in python code.

    This puts the timeout into a loop in application python code, so it does
    not block when using gevent/eventlet monkey patched workers.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _lock.acquire(block=False):
            break
        else:
            time.sleep(0.1)
    else:
        raise PrometheusLockTimeout('Timeout acquiring prometheus lock')

    yield
    _lock.release()


def setup_prometheus_multiproc(async_mode):
    """Setup prometheus_client multiprocess support.

    This involves setting up locking and a temporary directory if needed.

    Note: if we can't create the lock (e.g. inside a strictly confined snap
    package) then multiprocess cleanup is *not* enabled.
    """
    global _lock, registry, try_prometheus_lock
    if not prometheus_installed:
        return

    if 'prometheus_multiproc_dir' not in os.environ:
        prefix = 'prometheus_multiproc_{}_'.format(os.getpid())
        tmp = tempfile.mkdtemp(prefix=prefix)
        os.environ['prometheus_multiproc_dir'] = tmp

    # try enable multiprocess cleanup
    try:
        _lock = Lock()
    except OSError as exc:
        if exc.errno != errno.EACCES:
            raise

        early_log(
            __name__,
            'warning',
            'Unable to create lock for prometheus, cleanup disabled',
        )
    else:

        if async_mode:
            try_prometheus_lock = try_prometheus_lock_patched_async
        else:
            try_prometheus_lock = try_prometheus_lock_normal

        # signal to others that clean up is enabled
        talisker.prometheus_multiproc_cleanup = True

    early_log(
        __name__,
        'info',
        'prometheus_client is in multiprocess mode',
        extra={
            'multiproc_dir': os.environ['prometheus_multiproc_dir'],
            'cleanup_enabled': talisker.prometheus_multiproc_cleanup,
        }
    )


def collect_metrics():
    from prometheus_client import (
        CollectorRegistry,
        core,
        generate_latest,
        multiprocess,
    )
    if 'prometheus_multiproc_dir' in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = core.REGISTRY
    with try_prometheus_lock():
        return generate_latest(registry)


def _filter_exists(paths):
    exists = []
    for path in paths:
        if os.path.exists(path):
            exists.append(path)
    return exists


def prometheus_cleanup_worker(pid):
    """Aggregate dead worker's metrics into a single archive file."""
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(pid)  # this takes care of gauges
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
    collector = multiprocess.MultiProcessCollector(None)

    try:
        metrics = collector.merge(collect_paths, accumulate=False)
    except AttributeError:
        metrics = legacy_collect(collect_paths)

    tmp_histogram = tempfile.NamedTemporaryFile(delete=False)
    tmp_counter = tempfile.NamedTemporaryFile(delete=False)
    write_metrics(metrics, tmp_histogram.name, tmp_counter.name)

    try:
        # ensure reader does get partial state
        with try_prometheus_lock():
            os.rename(tmp_histogram.name, histogram_path)
            os.rename(tmp_counter.name, counter_path)

            for path in paths:
                os.unlink(path)
    except PrometheusLockTimeout:
        logging.getLogger(__name__).exception(
            'Failed to acquire prometheus lock to clean worker files',
            extra={
                'pid': pid,
                'paths': paths,
            }
        )


def get_mmaped_dict():
    """Helper to import MmapedDict for backward compatibility."""
    try:
        from prometheus_client.mmap_dict import MmapedDict
    except ImportError:
        from prometheus_client.core import _MmapedDict as MmapedDict
    return MmapedDict


def legacy_collect(files):
    """
    Almost verbatim from MultiProcessCollector.collect(), pre 0.4.0.

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
    mmaped_dict = get_mmaped_dict()

    try:
        # for prometheus-client>=0.6.0
        from prometheus_client.utils import floatToGoString
        from prometheus_client.metrics_core import Metric
    except ImportError:
        from prometheus_client.core import (
            Metric,
            _floatToGoString as floatToGoString)

    metrics = {}
    for f in files:
        if not os.path.exists(f):
            continue
        # verbatim from here...
        parts = os.path.basename(f).split('_')
        typ = parts[0]
        d = mmaped_dict(f, read_mode=True)
        for key, value in d.read_all_values():
            # Note: key format changed in 0.4+
            metric_name, name, labelnames, labelvalues = json.loads(key)

            metric = metrics.get(metric_name)
            if metric is None:
                metric = Metric(metric_name, 'Multiprocess metric', typ)
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
                        labels + (('le', floatToGoString(bucket)),),
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
    mmaped_dict = get_mmaped_dict()

    if prometheus_version >= parse_version('0.6.0'):
        from prometheus_client.mmap_dict import mmap_key
        key_func = mmap_key
    elif prometheus_version >= parse_version('0.4.0'):
        from prometheus_client.core import _mmap_key
        key_func = _mmap_key
    else:
        def key_func(metric_name, name, labelnames, labelvalues):
            return json.dumps(
                (metric_name, name, tuple(labels), tuple(labels.values()))
            )

    histograms = mmaped_dict(histogram_file)
    counters = mmaped_dict(counter_file)

    try:
        for metric in metrics:
            if metric.type == 'histogram':
                sink = histograms
            elif metric.type == 'counter':
                sink = counters
            else:
                continue

            for sample in metric.samples:
                # prometheus_client 0.4+ adds extra fields
                name, labels, value = sample[:3]
                key = key_func(
                    metric.name,
                    name,
                    tuple(labels),
                    tuple(labels.values()),
                )
                sink.write_value(key, value)
    finally:
        histograms.close()
        counters.close()
