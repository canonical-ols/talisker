#!/usr/bin/env python
#
# Note: this file is autogenerated from setup.cfg for older setuptools
#
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

DESCRIPTION = '''
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

.. image:: https://requires.io/github/canonical-ols/talisker/requirements.svg
    :target: https://requires.io/github/canonical-ols/talisker/requirements/
    :alt: Requirements Status

Talisker is an enhanced runtime for your WSGI application that aims to provide
a common operational platform for your python microservices.

It integrates with many standard python libraries to give you out-of-the-box
logging, metrics, error reporting, status urls and more.


Quick Start
-----------

Simply install Talisker via pip::

    pip install talisker

And then run your WSGI app with Talisker (as if it was regular gunicorn).::

    talisker.gunicorn app:wsgi -c config.py ...

This gives you 80% of the benefits of Talisker: structured logging, metrics,
sentry error handling, standardised status endpoints and more.


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
'''

setup(
    author='Simon Davy',
    author_email='simon.davy@canonical.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
        'Topic :: System :: Logging',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    description='A common WSGI stack',
    entry_points=dict(
        console_scripts=[
            'talisker=talisker:run_gunicorn',
            'talisker.run=talisker:run',
            'talisker.gunicorn=talisker:run_gunicorn',
            'talisker.gunicorn.eventlet=talisker:run_gunicorn_eventlet',
            'talisker.gunicorn.gevent=talisker:run_gunicorn_gevent',
            'talisker.celery=talisker:run_celery',
        ],
    ),
    extras_require=dict(
        django=[
            'django>=1.8,<1.11',
        ],
        dev=[
            'logging_tree',
            'pygments',
        ],
        pg=[
            'sqlparse>=0.2',
            'psycopg2>=2.7.0,<3.0',
        ],
        prometheus=[
            'prometheus-client>=0.0.17,<0.1',
        ],
        celery=[
            'celery>=3.1.13.0,<5.0',
        ],
        flask=[
            'flask>=0.11,<0.13',
            'blinker>=1.4,<2.0',
        ],
    ),
    include_package_data=True,
    install_requires=[
        'gunicorn>=19.5.0,<20.0',
        'Werkzeug>=0.11.5,<0.13',
        'statsd>=3.2.1,<4.0',
        'requests>=2.10.0,<3.0',
        'raven>=5.27.0,<7.0',
        'future>=0.15.2,<0.17',
        'ipaddress>=1.0.16,<2.0;python_version<"3.3"',
    ],
    keywords=[
        'talisker',
    ],
    license='GPL3',
    long_description=DESCRIPTION,
    name='talisker',
    package_data=dict(
        talisker=[
            'logstash/*',
        ],
    ),
    package_dir=dict(
        talisker='talisker',
    ),
    packages=[
        'talisker',
    ],
    test_suite='tests',
    url='https://github.com/canonical-ols/talisker',
    version='0.9.6',
    zip_safe=False,
)
