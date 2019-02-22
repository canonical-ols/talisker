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

`prometheus_client` integration has extensive support for
multiprocessing with gunicorn.

If you are only using one worker process, then regular single process
mode is used.

However, if you have multiple workers, then the
'prometheus_multiproc_dir' envvar is set to a tmpdir, as per
`the prometheus_client multiprocessing docs <>`.
This allows any worker being scraped to report metrics for all workers.

However, by default it leaks mmaped files when workers are killed,
wasting disk space and slowing down metric collection. Talisker provides
a non-trivial workaround for this, by having the gunicorn master merge
left over metrics into a single file.

Note that in multiprocss mode, due to prometheus_client's design, all
registiered metrics are exposed, regardless of registry

The metrics are exposed at ``/_status/metrics``
