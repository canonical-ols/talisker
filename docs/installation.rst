.. highlight:: shell

=====
Setup
=====

Installation
------------

In general, use pip to install::

    $ pip install talisker


Usage
-----

Talisker can be simply used in place of gunicorn.

To run the test server, try::

    $ TALISKER_DEVEL=1 talisker tests.server:reflect --bind 0.0.0.0

This app simply reflects the wsgi environ back at you.

The full options are below.

.. program-output:: talisker --help

