===============================
talisker
===============================

.. image:: https://img.shields.io/pypi/v/talisker.svg
        :target: https://pypi.python.org/pypi/talisker

.. image:: https://img.shields.io/travis/bloodearnest/talisker.svg
        :target: https://travis-ci.org/bloodearnest/talisker

.. image:: https://readthedocs.org/projects/talisker/badge/?version=latest
        :target: https://readthedocs.org/projects/talisker/?badge=latest
        :alt: Documentation Status


A common WSGI stack based on gunicorn

* Free software: GPL3 license
* Documentation: https://talisker.readthedocs.org.

Features
--------

A tool running python wsgi apps with gunicorn

Currently:

 - enhances stdlib logging with structured formatting
 - standard wsgi stack that provides
    - request id injection and logging
    - standard set of service status endpoints
 - simple app agnostic runner, zero* app configuration required

In future

 - raven/sentry middleware
 - requests session management
 - statsd
   - client managment
   - enabling/enhancing gunicorn statsd output


* for some value of zero


Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
