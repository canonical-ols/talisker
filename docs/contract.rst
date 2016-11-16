.. highlight:: python

========
Contract
========

There is nothing particularly Python-specific about what Talisker offers. The
basic contract of its behaviour and configuration could be provided in other
languages as well. This contract outlines the the basic requirements of an
implementation in order to be considered "compliant".

Logging
-------

DEBUBGLOG environment variable points to the debug log file.

1. Access logs to stderr.

2. Error logs to stderr.

3. Log format:

   format = '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"'
   datefmt = "%Y-%m-%d %H:%M:%S"

   which should look like this::

    2016-07-14 01:02:03.456Z INFO app "hello"

4. Generates a request ID if one isn't in the `X-Request-ID` header in the
   incoming request.


Endpoints
---------

1. `/_status/ping`

   A very simple server status check, to determine if the service is actually
   running.  An HTTP 200 response indicates success.

2. `/_status/check`

   A more thorough status check, to determine if the service is healthy.  This
   is intended to be consumed by something like Nagios to issue alerts in the
   event of failures.  Things to check here might include database
   connectivity, disk space and memory utilisation.  An HTTP 200 response
   indicates that the service is healthy.

3. `/_status/error`

   Generate an error that can be traced in the logs and error reporting
   backend.

4. `/_status/metric`

   Generate a metric that can be traced in a statsd collector such as graphite
   or grafana.

5. `/_status/info`

   Service info?


Statsd
------

Configured using the environment variable `STATSD_DSN`.


Sentry
------

Configured using the environment variable `SENTRY_DSN`.
