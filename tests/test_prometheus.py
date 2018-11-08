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
import os
import time

import pytest

import talisker
import talisker.metrics
from tests.test_metrics import Sample, counter_name
from tests.test_metrics import registry  # NOQA

from talisker import prometheus


@pytest.fixture
def clean_globals():
    "Save and restore module globals touched by setup_prometheus_multiproc."""
    prometheus_multiproc_cleanup = talisker.prometheus_multiproc_cleanup
    _lock = prometheus._lock
    try_prometheus_lock = prometheus.try_prometheus_lock

    # defaults
    talisker.prometheus_multiproc_cleanup = False
    prometheus._lock = None
    prometheus.try_prometheus_lock = prometheus.try_prometheus_lock_noop

    yield

    talisker.prometheus_multiproc_cleanup = prometheus_multiproc_cleanup
    prometheus._lock = _lock
    prometheus.try_prometheus_lock = try_prometheus_lock


def test_setup_prometheus_multiproc(clean_globals, context):
    assert talisker.prometheus_multiproc_cleanup is False
    assert (
        prometheus.try_prometheus_lock is prometheus.try_prometheus_lock_noop
    )

    prometheus.setup_prometheus_multiproc(async_mode=False)

    assert talisker.prometheus_multiproc_cleanup
    assert (
        prometheus.try_prometheus_lock is prometheus.try_prometheus_lock_normal
    )
    log = context.logs.find(
        level='info',
        msg='prometheus_client is in multiprocess mode',
        extra={'cleanup_enabled': True},
    )
    assert log is not None
    assert 'multiproc_dir' in log.extra


def test_setup_prometheus_multiproc_async(clean_globals, context):
    prometheus.setup_prometheus_multiproc(async_mode=True)

    assert (
        prometheus.try_prometheus_lock is
        prometheus.try_prometheus_lock_patched_async
    )


def test_setup_prometheus_multiproc_error(
        clean_globals, monkeypatch, context):
    """EACCES creating the multiprocess.Lock() should log a warning."""
    def fail(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr("talisker.prometheus.Lock", fail)

    prometheus.setup_prometheus_multiproc(async_mode=False)

    assert context.logs.exists(
        level='warning',
        msg='Unable to create lock for prometheus, cleanup disabled',
    )


def test_try_prometheus_lock_normal():
    with prometheus._lock:
        start = time.time()
        with pytest.raises(prometheus.PrometheusLockTimeout):
            with prometheus.try_prometheus_lock_normal(0.2):
                pass
        elapsed = time.time() - start
        assert elapsed < 0.5


def test_try_prometheus_lock_patched_async():
    with prometheus._lock:
        start = time.time()
        with pytest.raises(prometheus.PrometheusLockTimeout):
            with prometheus.try_prometheus_lock_patched_async(0.2):
                pass
        elapsed = time.time() - start
        assert elapsed < 0.5


def histogram_sorter(sample):
    # sort histogram samples in order of bucket size
    name, labels, _ = sample[:3]
    return name, float(labels.get('le', 0))


def test_prometheus_cleanup(registry):  # NOQA
    pid = 1

    def getpid():
        return pid

    # override use of os.getpid. _ValueClass is recreated after every test,
    # so we don't need to clean up
    from prometheus_client import core
    core._ValueClass = core._MultiProcessValue(getpid)

    histogram = talisker.metrics.Histogram(
        name='histogram',
        documentation='test histogram',
        labelnames=['foo', 'bar', 'baz'],
        statsd='{name}.{label}',
        registry=registry,
    )
    counter = talisker.metrics.Counter(
        name='counter',
        documentation='test counter',
        labelnames=['foo', 'bar', 'baz'],
        statsd='{name}.{label}',
        registry=registry,
    )

    from prometheus_client.multiprocess import MultiProcessCollector
    collector = MultiProcessCollector(registry)
    labels = {'foo': 'foo', 'bar': 'bar', 'baz': 'baz'}

    def collect():
        return {m.name: m for m in collector.collect()}

    def files():
        return list(sorted(os.listdir(os.environ['prometheus_multiproc_dir'])))

    counter.inc(1, **labels)
    histogram.observe(0.5, **labels)
    histogram.observe(2.5, **labels)

    assert files() == [
        'counter_1.db',
        'histogram_1.db',
    ]

    before = collect()
    prometheus.prometheus_cleanup_worker(pid)
    after = collect()
    assert files() == [
        'counter_archive.db',
        'histogram_archive.db',
    ]
    assert before == after

    # magic!
    pid += 1

    # new worker, create some new metrics, check they are all combined
    counter.inc(2, **labels)
    histogram.observe(0.5, **labels)
    histogram.observe(2.5, **labels)

    later = collect()
    assert files() == [
        'counter_2.db',
        'counter_archive.db',
        'histogram_2.db',
        'histogram_archive.db',
    ]

    # check counter is correct

    assert later['counter'].samples == [
        Sample(counter_name('counter_total'), labels, 3.0),
    ]

    expected_histogram = [
        Sample('histogram_bucket', dict(le='0.005', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.01', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.025', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.05', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.075', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.1', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.25', **labels), 0.0),
        Sample('histogram_bucket', dict(le='0.5', **labels), 2.0),
        Sample('histogram_bucket', dict(le='0.75', **labels), 2.0),
        Sample('histogram_bucket', dict(le='1.0', **labels), 2.0),
        Sample('histogram_bucket', dict(le='2.5', **labels), 4.0),
        Sample('histogram_bucket', dict(le='5.0', **labels), 4.0),
        Sample('histogram_bucket', dict(le='7.5', **labels), 4.0),
        Sample('histogram_bucket', dict(le='10.0', **labels), 4.0),
        Sample('histogram_bucket', dict(le='+Inf', **labels), 4.0),
        Sample('histogram_count', labels, 4.0),
        Sample('histogram_sum', labels, 6.0),
    ]

    # check histogram is correct
    later['histogram'].samples.sort(key=histogram_sorter)
    assert later['histogram'].samples == expected_histogram

    # check the final files produce the correct numbers
    prometheus.prometheus_cleanup_worker(pid)
    final = collect()
    assert files() == [
        'counter_archive.db',
        'histogram_archive.db',
    ]
    final['histogram'].samples.sort(key=histogram_sorter)
    assert later == final
