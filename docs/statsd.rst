.. highlight:: python


======
Statsd
======

Talisker provides statsd integration and configuration.

Configuration
-------------

Statsd can be configured by the STATSD_DSN envvar, patterned after the SENTRY_DSN.
This combines all statsd config into a single DSN url.

e.g.::

   # talk udp on port 1234 to host statsd, using a prefix of 'my.prefix'
   STATSD_DSN=udp://statsd:1234/my.prefix

   # can also use / for prefix separators, the / coverted to .
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

If statsd is configured, talsiker will configure gunicorn's statsd
functionality to use it.  Additionally, it will enable statsd metrics for
talisker's requests sessions.

Your app code can get a statsd client by simply calling:::

  statsd = talisker.statsd.get_client()

Note: this next section is still WIP. Document intended usage, following DDD.

Additionally, talisker supports a more efficient statsd flushing mechanism: pipelines.

It creates a statsd pipeline per request, and puts in the wsgi environment.
This pipeline client can be used by anything during that request, and is then
flushed when the request is completed.  This results in fewer udp packets being
sent, as several can be packed in to the same 512 byte packet. See the statsd
module's `pipeline documentation
<http://statsd.readthedocs.io/en/v3.2.1/pipeline.html>`_ for more information.



