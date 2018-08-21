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

import prometheus_client
import pytest

from talisker import metrics


@pytest.fixture()
def registry(monkeypatch, tmpdir):
    registry = prometheus_client.CollectorRegistry()

    def get_metric(name, **labels):
        value = registry.get_sample_value(name, labels)
        return 0 if value is None else value

    registry.get_metric = get_metric
    return registry


def test_histogram(statsd_metrics, registry):
    histogram = metrics.Histogram(
        name='test_histogram',
        documentation='test histogram',
        labelnames=['label'],
        statsd='{name}.{label}',
        registry=registry,
    )

    labels = {'label': 'value'}
    count = registry.get_metric('test_histogram_count', **labels)
    sum_ = registry.get_metric('test_histogram_sum', **labels)
    bucket = registry.get_metric('test_histogram_bucket', le='2.5', **labels)

    histogram.observe(2.0, **labels)

    assert statsd_metrics[0] == 'test.histogram.value:2.000000|ms'
    assert registry.get_metric('test_histogram_count', **labels) - count == 1.0
    assert registry.get_metric('test_histogram_sum', **labels) - sum_ == 2.0
    after_bucket = registry.get_metric(
        'test_histogram_bucket', le='2.5', **labels)
    assert after_bucket - bucket == 1.0


def test_histogram_protected(log, registry):
    histogram = metrics.Histogram(
        name='test_histogram_protected',
        documentation='test histogram',
        labelnames=['label'],
        statsd='{name}.{label}',
        registry=registry,
    )

    histogram.prometheus = 'THIS WILL RAISE'
    histogram.observe(1.0, label='label')
    assert log[0].msg == 'Failed to collect histogram metric'


def test_counter(statsd_metrics, registry):
    counter = metrics.Counter(
        name='test_counter',
        documentation='test counter',
        labelnames=['label'],
        statsd='{name}.{label}',
        registry=registry,
    )

    labels = {'label': 'value'}
    count = registry.get_metric('test_counter', **labels)
    counter.inc(2, **labels)

    assert statsd_metrics[0] == 'test.counter.value:2|c'
    assert registry.get_metric('test_counter', **labels) - count == 2


def test_counter_protected(log, registry):
    counter = metrics.Counter(
        name='test_counter_protected',
        documentation='test counter',
        labelnames=['label'],
        statsd='{name}.{label}',
    )

    counter.prometheus = 'THIS WILL RAISE'
    counter.inc(1, label='label')
    assert log[0].msg == 'Failed to increment counter metric'


def test_prometheus_cleanup(registry):
    pid = 1

    def getpid():
        return pid

    # override use of os.getpid. _ValueClass is recreated after every test,
    # so we don't need to clean up
    from prometheus_client import core
    core._ValueClass = core._MultiProcessValue(getpid)

    histogram = metrics.Histogram(
        name='histogram',
        documentation='test histogram',
        labelnames=['foo', 'bar', 'baz'],
        statsd='{name}.{label}',
        registry=registry,
    )
    counter = metrics.Counter(
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
    metrics.prometheus_cleanup_worker(pid)
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
    assert later['counter'].samples == [('counter', labels, 3.0)]

    expected_histogram = [
        ('histogram_bucket', dict(le='0.005', **labels), 0.0),
        ('histogram_bucket', dict(le='0.01', **labels), 0.0),
        ('histogram_bucket', dict(le='0.025', **labels), 0.0),
        ('histogram_bucket', dict(le='0.05', **labels), 0.0),
        ('histogram_bucket', dict(le='0.075', **labels), 0.0),
        ('histogram_bucket', dict(le='0.1', **labels), 0.0),
        ('histogram_bucket', dict(le='0.25', **labels), 0.0),
        ('histogram_bucket', dict(le='0.5', **labels), 2.0),
        ('histogram_bucket', dict(le='0.75', **labels), 2.0),
        ('histogram_bucket', dict(le='1.0', **labels), 2.0),
        ('histogram_bucket', dict(le='2.5', **labels), 4.0),
        ('histogram_bucket', dict(le='5.0', **labels), 4.0),
        ('histogram_bucket', dict(le='7.5', **labels), 4.0),
        ('histogram_bucket', dict(le='10.0', **labels), 4.0),
        ('histogram_bucket', dict(le='+Inf', **labels), 4.0),
        ('histogram_count', labels, 4.0),
        ('histogram_sum', labels, 6.0),
    ]

    # check histogram is correct
    later['histogram'].samples.sort(key=metrics.histogram_sorter)
    assert later['histogram'].samples == expected_histogram

    # check the final files produce the correct numbers
    metrics.prometheus_cleanup_worker(pid)
    final = collect()
    assert files() == [
        'counter_archive.db',
        'histogram_archive.db',
    ]
    final['histogram'].samples.sort(key=metrics.histogram_sorter)
    assert later == final
