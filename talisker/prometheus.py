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
from contextlib import contextmanager
from multiprocessing import Lock
import errno
import logging
import os
import tempfile
import time

import talisker
from talisker.util import (
    early_log,
    pkg_is_installed,
    TaliskerVersionException,
)


prometheus_installed = pkg_is_installed('prometheus_client')
if prometheus_installed and prometheus_installed.version in ('0.4.0', '0.4.1'):
    raise TaliskerVersionException(
        'prometheus_client {} has a critical bug in multiprocess mode, '
        'and is not supported in Talisker. '
        'https://github.com/prometheus/client_python/issues/322'.format(
            prometheus_installed.version,
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

    metrics = collector.merge(collect_paths, accumulate=False)

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


def write_metrics(metrics, histogram_file, counter_file):
    from prometheus_client.mmap_dict import MmapedDict, mmap_key

    histograms = MmapedDict(histogram_file)
    counters = MmapedDict(counter_file)

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
                key = mmap_key(
                    metric.name,
                    name,
                    tuple(labels),
                    tuple(labels.values()),
                )
                sink.write_value(key, value)
    finally:
        histograms.close()
        counters.close()
