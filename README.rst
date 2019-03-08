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

.. image:: https://img.shields.io/lgtm/grade/python/g/canonical-ols/talisker.svg?logo=lgtm&logoWidth=18
    :target: https://lgtm.com/projects/g/canonical-ols/talisker/
    :alt: Python code quality (LGTM)

.. image:: https://img.shields.io/lgtm/alerts/g/canonical-ols/talisker.svg?logo=lgtm&logoWidth=18
    :target: https://lgtm.com/projects/g/canonical-ols/talisker/
    :alt: LGTM alerts

Talisker is an enhanced runtime for your WSGI application that aims to provide
a common operational platform for your python microservices.

It integrates with many standard python libraries to give you out-of-the-box
logging, metrics, error reporting, status urls and more.


Quick Start
-----------

Simply install Talisker with Gunicorn via pip::

    pip install talisker[gunicorn]

And then run your WSGI app with Talisker (as if it was regular gunicorn).::

    talisker.gunicorn app:wsgi -c config.py ...

This gives you 80% of the benefits of Talisker: structured logging, metrics,
sentry error handling, standardised status endpoints and more.

Note: right now, Talisker has extensive support for running with Gunicorn, with
more WSGI server support planned.


Elevator Pitch
--------------

Talisker integrates and configures standard python libraries into a single
tool, useful in both development and production. It provides:

  - structured logging for stdlib logging module (with grok filter)
  - gunicorn as a wsgi runner
  - request id tracing
  - standard status endpoints
  - statsd/prometheus metrics for incoming/outgoing http requests and more.
  - deep sentry integration

It also optionally supports the same level of logging/metrics/sentry
integration for:

 - celery workers
 - general python scripts, like cron jobs or management tasks.

Talisker is opinionated, and designed to be simple to use. As such, it is not
currently very configurable. However, PR's are very welcome!

For more information, see The Documentation, which should be found at:

https://talisker.readthedocs.io
