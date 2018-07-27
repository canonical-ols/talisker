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

from prometheus_client import REGISTRY

import talisker.metrics


def get_metric(name, **labels):
    value = REGISTRY.get_sample_value(name, labels)
    return 0 if value is None else value


def test_historgram(statsd_metrics):
    histogram = talisker.metrics.Histogram(
        name='test_histogram',
        documentation='test histogram',
        labelnames=['label'],
        statsd='{name}.{label}',
    )

    labels = {'label': 'value'}
    count = get_metric('test_histogram_count', **labels)
    sum = get_metric('test_histogram_sum', **labels)
    bucket = get_metric('test_histogram_bucket', le='2.5', **labels)

    histogram.observe(2.0, **labels)

    assert statsd_metrics[0] == 'test.histogram.value:2.000000|ms'
    assert get_metric('test_histogram_count', **labels) - count == 1.0
    assert get_metric('test_histogram_sum', **labels) - sum == 2.0
    after_bucket = get_metric('test_histogram_bucket', le='2.5', **labels)
    assert after_bucket - bucket == 1.0


def test_counter(statsd_metrics):
    counter = talisker.metrics.Counter(
        name='test_counter',
        documentation='test counter',
        labelnames=['label'],
        statsd='{name}.{label}',
    )

    labels = {'label': 'value'}
    count = get_metric('test_counter', **labels)
    counter.inc(2, **labels)

    assert statsd_metrics[0] == 'test.counter.value:2|c'
    assert get_metric('test_counter', **labels) - count == 2
