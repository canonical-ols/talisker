.. highlight:: python


========
Requests
========

Enhanced session
----------------

Talisker provides a way to upgrade a request.Session instance with a few extra
features.

Firstly, the X-Request-Id header will be added to the outgoing request headers.
This can be used by other services to track the originating request id. We
usually append incoming request id to one generated for that request, e.g.::

   X-Request-Id: <generated request id>-<incoming request id>.

This allows simple searches to uncover all related sub requests for a specific
request, also known as fanout.

Secondly, we also collect metrics for outgoing requests. Specifically:

* counter for all requests, broken down by host and view
* counter for errors, broken down by host, type (http 5xx or connection error),
  view and error code (either POSIX error code or http status code, depending
  on type)
* histogram for duration of http responses

In statsd, they would be named like so::

    <prefix>.requests.count.<host>.<view>
    <prefix>.requests.errors.<host>.<type>.<view>.<code>
    <prefix>.requests.timeouts.<host>.<view>
    <prefix>.requests.latency.<host>.<view>.<status>

Note: a view here is a human friendly name for the api/endpoint. If the
upstream service returns an X-View-Name header in its response (e.g. is another
talisker service), or if the user has given this call a name (see below), then
this will be used.

You can customise the name of this metric if you wish, with some keyword arguments::

    session.post(..., metric_api_name='myapi', metric_host_name='myservice')

will use these values in the resulting naming, in both prometheus and statsd.::

    <prefix>.requests.count.myservice.myapi...



Session lifecycle
-----------------

We found many of our services were not using session objects properly, often
creating/destroying them per-request, thus not benefiting from the default
connection pooling provided by requests. This is especially painful for latency
when your upstream services are https, as nearly all ours are. But sessions are
not thread-safe (see `this issue
<https://github.com/kennethreitz/requests/issues/1871>`_ for details), sadly,
so a global session is risky.

So, talisker helps by providing a simple way to have thread local sessions.


Using a talisker session
------------------------

To get a base requests.Session thread local session with metrics and request id
tracing:::

  session = talisker.requests.get_session()

or use the wsgi environ::

  session = environ['requests']

If you wish to use a custom subclass of Session rather than the default
requests.Session, just pass the session class as an argument. Talisker will
ensure there is one instance of this session subclass per thread.::

  session = talisker.requests.get_session(MyCustomSessionClass)

This works because talisker does not subclass Session to add metrics or
requests id tracing. Instead, it adds a response hook to the session object for
metrics, and decorates the send method to inject the header (ugh, but
I couldn't find a better way).

If you wish to use talisker's enhancements, but not the lifecycle management,
you can do::

  session = MySession()
  talisker.requests.configure(session)

and session will now have metrics and id tracing.
