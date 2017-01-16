.. highlight:: python


======
Sentry
======

Talisker provides out-of-the-box integration with sentry.

Specifically, talisker adds:

 * some default configuation of the sentry client
 * sentry wsgi middleware
 * sentry error log handler (for logged exception messages)
 * log messge breadcrumbs (more breadcrumbs is a TODO)
 * sentry integration with flask, django, and celery

To get the current sentry client, simply use::

    talisker.sentry.get_client()

Error Data
----------

Talisker configures sentry breadcrumbs for log messages at INFO or higher level.
It also addes the request id as a tag to the sentry message.

If you want to add some custom error context, you can use the client above as you
would use the sentry client as normal.

e.g.::

    client = talisker.sentry.get_client()
    client.context.merge({'tags': my_tags})


Sentry Configuration
--------------------

Talisker uses the default SENTRY_DSN env var to configure sentry by
default.  Simply setting this will enable sentry for wsgi and logging.

In addition, talisker configures the sentry client by default as follows:

 - sets `install_logging_hook=False`, as talisker handles it
 - sets `release` to the current :ref:`revision`
 - sets `hook_libraries=[]`, disabling breadcrumbs for request/httplib
 - sets `environment` to TALISKER_ENVIRONMENT envvar
 - sets `name` to TALISKER_UNIT envvar
 - sets `site` to TALISKER_DOMAIN envvar
 - ensures the RemovePostDataProcessor, SanitizePasswordsProcessor, and
   RemoveStackLocalsProcessor processors are always included, to be safe by
   default.


If you are using Talisker's :ref:`flask` or :ref:`django` integration, you can configure
your sentry client further via the usual config methods for those frameworks.

If you wish to manually configure the sentry client, use the following::

    talisker.sentry.set_client(**config)

This will reconfigure and reset the sentry client used by the wsgi middleware
and logging handler that Talisker sets up.

Whichever way you wish to configure sentry, talisker will honour your
configuration except for 2 things

1) `install_logging_hook` will always be set to false, or else you'll get
   duplicate exceptions logged to sentry.

2) the processors will always include the base 3, although you can add more.
   This may change in future.
