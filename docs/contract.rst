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

The ``DEBUGLOG`` environment variable tells Talisker where to write the debug log file.

1. Log format::

    FORMAT = '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"'
    DATEFMT = "%Y-%m-%d %H:%M:%S"

   Where ``message`` is the formatted log message, with any extra parameters
   appended as ``key=value`` pairs. The resulting log entry should look like this::

    2016-07-14 01:02:03.456Z INFO app "hello" key=value key2=value2

2. Access logs to stderr::

    2016-11-16 17:54:14.124Z INFO gunicorn.access "GET /" method=GET path=/ qs= status=400 ip=127.0.0.1 proto=HTTP/1.1 length=121 referrer=None ua=curl/7.35.0 duration=28.525 request_id=00cf39ce-47a2-402d-9336-80555d2fd268

3. Error logs to stderr::

    2016-11-16 17:59:18.237Z ERROR gunicorn.error "Error handling request /_status/error" request_id=5baf01d6-1326-4383-a734-fbcdbf7b8e10
    Traceback (most recent call last):
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/gunicorn/workers/sync.py", line 135, in handle
        self.handle_request(listener, req, client, addr)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/gunicorn/workers/sync.py", line 176, in handle_request
        respiter = self.wsgi(environ, resp.start_response)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/werkzeug/local.py", line 228, in application
        return ClosingIterator(app(environ, start_response), self.cleanup)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/wsgi.py", line 52, in middleware
        return app(environ, custom_start_response)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/request_id.py", line 105, in __call__
        return self.app(environ, add_id_header)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/wsgi.py", line 42, in middleware
        return app(environ, start_response)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/endpoints.py", line 110, in __call__
        response = func(request)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/endpoints.py", line 71, in wrapper
        return f(self, request)
      File "/home/talisker/src/talisker-service/env/lib/python3.4/site-packages/talisker/endpoints.py", line 161, in error
        raise TestException('this is a test, ignore')
    talisker.endpoints.TestException: this is a test, ignore

4. Generates a request ID if one isn't in the ``X-Request-ID`` header in the
   incoming request.


Endpoints
---------

1. ``/_status/ping``

   A very simple server status check, to determine if the service is actually
   running.  An HTTP 200 response indicates success.

2. ``/_status/check``

   A more thorough status check, to determine if the service is healthy.  This
   is intended to be consumed by something like Nagios to issue alerts in the
   event of failures.  Things to check here might include database
   connectivity, disk space and memory utilisation.  An HTTP 200 response
   indicates that the service is healthy.

3. ``/_status/error``

   Generate an error that can be traced in the logs and error reporting
   backend.

4. ``/_status/metric``

   Generate a metric that can be traced in a statsd collector such as graphite
   or grafana.

5. ``/_status/info``

   Service info?


Statsd
------

Integration with statsd may be configured using the environment variable
``STATSD_DSN``, which should be a standard URL, e.g.::

    udp://statsd-host:8125/prefix

Sentry
------

Configured using the environment variable ``SENTRY_DSN``.
