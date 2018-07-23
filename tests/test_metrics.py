#
# Copyright (c) 2015-2018 Canonical, Ltd.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
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
