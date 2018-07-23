##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import talisker.statsd


try:
    import prometheus_client
except ImportError:
    prometheus_client = False

try:
    import statsd
except ImportError:
    statsd = False


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


class Histogram(Metric):

    @property
    def metric_type(self):
        return prometheus_client.Histogram

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
