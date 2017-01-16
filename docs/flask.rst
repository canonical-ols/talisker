.. highlight:: python


=====
Flask
=====

Usage
-----

Talisker provides some opt-in support for flask apps. This does two main things currently.

1) enable sentry flask support for your app. This means you will get more
   information in your sentry errors, as well as being able to configure sentry
   via your app config as normal.

2) disable flask default app logger configuration, and just use taliskers
   configuration.  This avoids double logged exception messages.

To enable, you can either use a special Talisker flask app::

    app = talisker.flask.TaliskerApp(__name__)

or register your app with Talisker afterwards::

    talisker.flask.register(app)


Sentry Details
--------------

Talisker integrates the flask support in ```raven.contrib.flask```. See `the
raven flask documentation
<https://docs.sentry.io/clients/python/integrations/flask/>`_ for more details.

The sentry flask extension is configured to work with talisker.

 * ```logging=False``` as Talisker has already set this up. This means the
   other possible logging config is ignored.

 * ```wrap_wsgi=False``` as Talisker has already set this up

 * ```register_signal=True```, which is the default

If for some reason you with to configure the flask sentry extension yourself::

    talisker.flask.sentry(app, **config)

This has the same api as the default ```raven.contrib.flask.Sentry``` object,
but with the above configuration.
