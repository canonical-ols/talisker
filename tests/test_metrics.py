# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

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
