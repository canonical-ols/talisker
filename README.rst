===========================================
Talisker - an opinionated WSGI app platform
===========================================

.. image:: https://img.shields.io/pypi/v/talisker.svg
    :target: https://pypi.python.org/pypi/talisker
    :remote:

.. image:: https://img.shields.io/travis/canonical-ols/talisker.svg
    :target: https://travis-ci.org/canonical-ols/talisker
    :remote:

.. image:: https://readthedocs.org/projects/talisker/badge/?version=latest
    :target: https://readthedocs.org/projects/talisker/?badge=latest
    :alt: Documentation Status
    :remote:


Talisker is a runtime for your wsgi app that aims to provide a common
platform for your python services.

tl;dr
-----

Simply run your wsgi app with talisker as if it was gunicorn.:

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
 - raven for errors
 - werkzeug for thread locals and wsgi utilities

It is designed specifically to be used in both development and production,
and aims to provide a default set of features out of the box:

  - drop-in replacement for gunicorn
  - standard log format, including ISO/UTC timestamps
  - structured logging with python stdlib
  - improved gunicorn access logs, with ms precision UTC timestamps
  - request id tracing
  - standard set of status endpoints for your app
  - easier statsd endpoint configuration
  - automatic prometheus metrics endpoint (optional)
  - sentry/raven middleware (TODO)

All the above are available by just using the talisker entry point script,
rather than gunicorn.

In addition, with a small amount of effort, your app can benefit from additional features:

  - simple deeper nagios checks - just implement a _status/check url in your app
  - per-thread requests connection pool managment (WIP)
  - automatic statsd metrics for outgoing HTTP requests (WIP)
  - more efficient statsd client management (WIP)

Additionally, talisker provides additional tools for integrating with your
infrastructure:

  - grok filters for log parsing (WIP)
  - rsyslog templates and config for log shipping (TODO)

Talisker is opinionated, and derived directly from the authors' needs and
as such not currently very configurable. However, PR's are very welcome!

For more information, see The Documentation, which should be found at:

https://talisker.readthedocs.io
