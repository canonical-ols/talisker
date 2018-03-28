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
