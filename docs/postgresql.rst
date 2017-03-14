.. highlight:: python


==========
Postgresql
==========

Talisker provides some optional integration with postgresql via pyscopg2, in
the form of a custom connection/cursor implementation that integrates with
logging and with sentry breadcrumbs.

To use it in Django::

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            ...
            'OPTIONS': {
                'connection_factory': talisker.postgresql.TaliskerConnection
            }
        }
    }

To use with sqlalchemy::

    TODO


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
the query parameters. In this case, we remove the rendered query parameters
from the string, in a kind of 'reverse parameterisation', in order to be sure
query parameter values are not sent externally


Slow query Logging
------------------

The connection logs slow queries to the `talisker.slowqueries` logger. The
default timeout is 5000ms, but can be controlled with the
TALISKER_SLOWQUERY_TIME env var.


Sentry Breadcrumbs
------------------

Talisker will capture all queries run during a request or other context as
Sentry breadcrumbs. In the case of an error, they will include them in the
report to sentry.
