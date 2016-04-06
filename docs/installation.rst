.. highlight:: shell

=====
Setup
=====

Installation
------------

At the command line::

    $ easy_install talisker

Or, if you have virtualenvwrapper installed::

    $ mkvirtualenv talisker
    $ pip install talisker


Usage
-----

Talisker can be simply used in place of gunicorn.

To run the test server, try::

    $ talisker_gunicorn test --devel -- tests.server:reflect --bind 0.0.0.0

This app simply reflects the wsgi environ back at you.

The full options are below.

.. program-output:: talisker_gunicorn --help
