.. highlight:: python


==========
Postgresql
==========

Talisker provides some optional integration with postgresql via pyscopg2, in
the form of a custom connection/cursor implementation that integrates with
logging and with sentry breadcrumbs.

Ensure you have the correct dependencies by using the `pg` extra::

   pip install talisker[pg]

To use it in Django::

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            ...,
            'OPTIONS': {
                'connection_factory': talisker.postgresql.TaliskerConnection
            }
        }
    }

To use with sqlalchemy::

    engine = sqlalchemy.create_engine(
        ...,
        connect_args={'connection_factory': talisker.postgresql.TaliskerConnection},
    )


Query Security
--------------

Given the security sensitive nature of raw sql queries, Talisker is very
cautious about what it might communicate externally, either via logs or via
sentry.

Talisker will only ever log the query string with placeholders, and never the
query parameters. This avoids leakage of sensitive information altogether,
while still providing enough info to be useful to users trying to debug problems.
If a query does not use query parameter, the query string is not sent, as there
is no way to determine if it is senstive or not.

One exception to this is stored procedures with parameters. The only access to
the query is via the raw query that was actually run, which has already merged
the query parameters, so we never send the raw query.

Note: in the future, we plan to add support for customised query sanitizing

Slow query Logging
------------------

The connection logs slow queries to the `talisker.slowqueries` logger. The
default timeout is -1, which disables slow query logging, but can be controlled with the
TALISKER_SLOWQUERY_TIME env var. If DEVEL envar is set, the default is 0, and
Talisker will log every query.


Sentry Breadcrumbs
------------------

Talisker will capture all queries run during a request or other context as
Sentry breadcrumbs. In the case of an error, they will include them in the
report to sentry.
