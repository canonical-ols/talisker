#!/usr/bin/env python
#
# Copyright (c) 2015-2021 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

DESCRIPTION = '''
===========================================
Talisker - an opinionated WSGI app platform
===========================================

.. image:: https://github.com/canonical-ols/talisker/actions/workflows/tox.yml/badge.svg?branch=master
   :target: https://github.com/canonical-ols/talisker/actions?workflow=tox
   :alt: CI Status

.. image:: https://readthedocs.org/projects/talisker/badge/?version=latest
    :target: https://readthedocs.org/projects/talisker/?badge=latest
    :alt: Documentation Status

Talisker is an enhanced runtime for your WSGI application that aims to provide
a common operational platform for your python microservices.

It integrates with many standard python libraries to give you out-of-the-box
logging, metrics, error reporting, status urls and more.

Python version support
----------------------

Talisker 0.20.0 was the last to support Python 2.7.
Talisker version >=0.21.0 only supports Python 3.x, as
they come with Ubuntu LTS releases.

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
'''

setup(
    author='Simon Davy',
    author_email='simon.davy@canonical.com',
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
        'Topic :: System :: Logging',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    description='A common WSGI stack',
    entry_points=dict(
        console_scripts=[
            'talisker=talisker:run_gunicorn[gunicorn]',
            'talisker.run=talisker:run',
            'talisker.gunicorn=talisker:run_gunicorn[gunicorn]',
            'talisker.gunicorn.eventlet=talisker:run_gunicorn_eventlet[gunicorn]',
            'talisker.gunicorn.gevent=talisker:run_gunicorn_gevent[gunicorn]',
            'talisker.celery=talisker:run_celery[celery]',
            'talisker.help=talisker:run_help',
        ],
    ),
    extras_require=dict(
        asyncio=[
        ],
        celery=[
            'celery>=4.3',
        ],
        dev=[
            'logging_tree>=1.9',
            'pygments>=2.11',
            'psutil>=5.9',
            'objgraph>=3.5',
        ],
        django=[
            'django<5',
        ],
        flask=[
            'flask<4',
            'blinker<2',
        ],
        gevent=[
            'gevent>=20.9.0',
        ],
        gunicorn=[
            'gunicorn>=19.9.0',
        ],
        pg=[
            'sqlparse>=0.4.2',
            'psycopg2>=2.8.4,<3.0',
        ],
        prometheus=[
            'prometheus-client<0.8',
        ],
        raven=[
            'raven>=6.4.0',
        ],
    ),
    include_package_data=True,
    install_requires=[
        'Werkzeug<4',
        'statsd<5',
        'requests<3.0',
    ],
    keywords=[
        'talisker',
    ],
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
    version='0.23.0',
    zip_safe=False,
)
