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

import prometheus_client
import pytest

from talisker import metrics

try:
    from prometheus_client.core import Sample

    def counter_name(n):
        return n

except ImportError:
    # prometheus_client < 0.4
    from collections import namedtuple
    Sample = namedtuple('Sample', ['name', 'labels', 'value'])

    def counter_name(n):
        return n[:-6]


@pytest.fixture()
def registry(monkeypatch, tmpdir):
    registry = prometheus_client.CollectorRegistry()

    def get_metric(name, **labels):
        value = registry.get_sample_value(name, labels)
        return 0 if value is None else value

    registry.get_metric = get_metric
    return registry


def test_histogram(context, registry):
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

    assert context.statsd[0] == 'test.histogram.value:2.000000|ms'
    assert registry.get_metric('test_histogram_count', **labels) - count == 1.0
    assert registry.get_metric('test_histogram_sum', **labels) - sum_ == 2.0
    after_bucket = registry.get_metric(
        'test_histogram_bucket', le='2.5', **labels)
    assert after_bucket - bucket == 1.0


def test_histogram_protected(context, registry):
    histogram = metrics.Histogram(
        name='test_histogram_protected',
        documentation='test histogram',
        labelnames=['label'],
        statsd='{name}.{label}',
        registry=registry,
    )

    histogram.prometheus = 'THIS WILL RAISE'
    histogram.observe(1.0, label='label')
    assert context.logs.exists(msg='Failed to collect histogram metric')


def test_counter(context, registry):
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

    assert context.statsd[0] == 'test.counter.value:2|c'
    metric = registry.get_metric(counter_name('test_counter_total'), **labels)
    assert metric - count == 2


def test_counter_protected(context, registry):
    counter = metrics.Counter(
        name='test_counter_protected',
        documentation='test counter',
        labelnames=['label'],
        statsd='{name}.{label}',
    )

    counter.prometheus = 'THIS WILL RAISE'
    counter.inc(1, label='label')
    assert context.logs.exists(msg='Failed to increment counter metric')
