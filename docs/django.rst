.. highlight:: python

.. _django:

======
Django
======

Talisker provides opt-in support for django apps.

.. _django_logging:

Logging
-------

To integrate with Talisker, you should at a minimum disable django's default
logging in your settings.py::

    LOGGING_CONFIG = None

If you don't, you'll get Django's `default logging configuration
<https://docs.djangoproject.com/en/1.10/topics/logging/#django-s-default-logging-configuration>`_
in addition to Talisker's, leading to some duplicated logs in
development, and possibly emails of errors in production, which is often
not a good idea.

If you have custom logging you want to add on top of Talisker's, you can
follow the Django documentation for `configuring logging yourself
<https://docs.djangoproject.com/en/1.10/topics/logging/#disabling-logging-configuration>`_,
with something like::

    LOGGING = {...}
    LOGGING_CONFIG = None
    import logging.config
    logging.config.dictConfig(LOGGING)

which is excactly what Django does, but without the default logging.

Sentry
------

To integrate with Talisker's sentry support, add raven to INSTALLED_APPS
as normal, and also set SENTRY_CLIENT in your settings.py::

    INSTALLED_APPS = [
        'raven.contrib.django.raven_compat',
        ...
    ]
    SENTRY_CLIENT = 'talisker.django.SentryClient'


This will ensure the extra info Talsiker adds to Sentry messages will be
applied, and also that the WSGI and logging handlers will use your Sentry
configuration in settings.py. It will also set `install_sql_hook=False`, as
that leaks raw SQL to the sentry server for every query. This will
hopefully be addressed in a future release.


Metadata
--------

Talisker supports the use of X-View-Name header for better introspection. This
is used for metric and logging information, to help debugging.

To support this in django, simply add the following middleware, in any order::

    MIDDLEWARE = [
        ...
        'talisker.django.middleware',
    ]


Management Tasks
----------------

If you use management tasks, and want them to run with Talisker logging,
you can use the generic talisker runner:

.. code-block:: bash

    talisker.run manage.py ...

or

.. code-block:: bash

    python -m talisker manage.py ...
