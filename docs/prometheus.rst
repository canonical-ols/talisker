.. highlight:: python


==========
Prometheus
==========

Talisker provides optional `prometheus_client` integration and configuration.

Installation
------------

The package supports extras args to install `prometheus_client`:

.. code-block:: bash

    $ pip install talisker[prometheus]

Configuration
-------------

`prometheus_client` integration needs no extra configuration if running
in single process mode.

If the app is running in `multiprocess mode <https://github.com/prometheus/client_python#multiprocess-mode-gunicorn>`_
(ie. with multiple workers), the `prometheus_multiproc_dir` envvar should be set
to a writable directory that can be used for metrics. If this envvar is not found,
a temporary directory will be created and used instead (but note that metrics will be reset
on restarts).

A default `worker_exit <http://docs.gunicorn.org/en/stable/settings.html#worker-exit>`_
server hook is automatically set up for cleaning up the shared
prometheus directory as well. Note that this can be overridden
by user supplied configuration, and in that case the custom `worker_exit` function
should perform the cleanup itself.

Integration
-----------

If `prometheus_client` is installed, Talisker will expose metrics collected by the
app using the default registry. Custom registries are only supported in multiprocess mode.
Metrics are available at ``/_status/metrics`` in Prometheus text format.
