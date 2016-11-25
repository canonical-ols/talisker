.. highlight:: python


==========
Prometheus
==========

Talisker provides optional `prometheus_client` integration and configuration.


Installation
------------

The package supports extras args to install `prometheus_client`::

    $ pip install talisker[prometheus]

Configuration
-------------

`prometheus_client` integration needs no extra configuration if running
in single process mode.

If the app is running in multiprocess mode (ie. with multiple workers), the
`prometheus_multiproc_dir` envvar must be set to a writable directory that can be used
for metrics.

Integration
-----------

If `prometheus_client` is installed, Talisker will expose metrics collected by the
app using the default registry. Custom registries are only supported in multiprocess mode.
Metrics are available at /_status/metrics in Prometheus text format.
