
===========================================
Talisker - an opinionated WSGI app platform
===========================================

.. image:: https://img.shields.io/pypi/v/talisker.svg
    :target: https://pypi.python.org/pypi/talisker

.. image:: https://img.shields.io/travis/canonical-ols/talisker.svg
    :target: https://travis-ci.org/canonical-ols/talisker

.. image:: https://readthedocs.org/projects/talisker/badge/?version=latest
    :target: https://readthedocs.org/projects/talisker/?badge=latest
    :alt: Documentation Status


Talisker is a runtime for your wsgi app that aims to provide a common
platform for your python services.

tl;dr
-----

Simply run your wsgi app with talisker as if it was gunicorn.::

    talisker app:wsgi -c config.py ...

Talisker will wrap your app in a some simple WSGI middleware, and configure
logging to output structured logging like so::

    logger = logging.getLogger('app')
    logger.info('something happened', extra={'context': 'I haz it'})

will output::

    2016-01-13 10:24:07.357Z INFO app "something happened" svc.context="I haz it" request_id=...

It also exposes some status endpoints you can use, go to the /_status/
url on your app to see them.

This all works out of the box by using the talisker runner instead of
gunicorn's, and there are many more features you can use too.


Elevator Pitch
--------------

Talisker is based on a number of standard python tools:

 - stdlib logging for logs
 - gunicorn for a wsgi runner
 - requests for http requests
 - statsd for metrics (and optionally, `prometheus_client`)
 - sentry for errors
 - werkzeug for thread locals and wsgi utilities

It also supports additionaly optional tools:

 - celery for async tasks
 - prometheus as an alternate metrics tool

It's main job is to integrate and configure all the above in a single tool, for
use in both dev and production, which provides a standard set of features out
of the box:

  - drop-in replacement for gunicorn as a wsgi runner
  - standardised structured logging on top of python stdlib logging
  - request id tracing
  - standard set of status endpoints for your app
  - easier configuration via env vars
  - metrics for *everything*
  - deep sentry integration (WIP)


All the above are available by just using the talisker entry point script,
rather than gunicorn.

In addition, with a small amount of effort, your app can benefit from additional features:

  - add structured logging tags to your application logs
  - simple deeper nagios checks - just implement a ``/_status/check`` url in your app
  - per-thread requests connection pool management

Additionally, talisker provides additional tools for integrating with your
infrastructure:

  - grok filters for log parsing
  - rsyslog templates and config for log shipping (TODO)

Talisker is opinionated, and derived directly from the authors' needs and
as such not currently very configurable. However, PR's are very welcome!

For more information, see The Documentation, which should be found at:

https://talisker.readthedocs.io
