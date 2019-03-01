.. highlight:: python


======
Statsd
======

Talisker provides statsd integration and configuration.

Configuration
-------------

Statsd can be configured by the STATSD_DSN envvar, patterned after the SENTRY_DSN.
This combines all statsd config into a single DSN url. For example::

.. code-block:: bash

   # talk udp on port 1234 to host statsd, using a prefix of 'my.prefix'
   STATSD_DSN=udp://statsd:1234/my.prefix

   # can also use / for prefix separators, the / converted to .
   STATSD_DSN=udp://statsd:1234/my/prefix

   # ipv6
   STATSD_DSN=udp6://statsd:1234/my.prefix

   # custom max udp size of 1024
   STATSD_DSN=udp://statsd:1234/my.prefix?maxudpsize=1024

Currently, only the udp statsd client is supported.  If no config is
provided, a dummy client is used that does nothing.

TODO: contribute this to upstream statsd module

Integration
-----------

If statsd is configured, talisker will configure
`gunicorn's statsd <http://docs.gunicorn.org/en/latest/instrumentation.html>`_
functionality to use it.  Additionally, it will enable statsd metrics for
talisker's requests sessions.

Your app code can get a statsd client by simply calling:::

  statsd = talisker.statsd.get_client()
