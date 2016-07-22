.. highlight:: python


========
Requests
========

Enhanced session
----------------

Talisker provides a way to upgrade a request.Session instance with two main
extra features.

Firstly, the X-Request-Id header will be added to the outgoing request headers.
This can be used by other services to track the originating request id. We
usually append in comming request id to one generated for that request, e.g.::

   X-Request-Id: <generated request id>-<incoming request id>.

This allows simple searches to uncover all related sub requests for a specific
request, also known as fanout.

Secondly, we also add statsd metrics for outgoing requests durations. Each
request will generate one timer statsd metric for request duration, with a name
in the form:::

  <prefix>.requests.<hostname>.<method>.<status code>

In the hostname, a '.' is replace with a '-'. So a http request like this:::

  session.post('https://somehost.com/some/url', data=...)

would result in the duration of that request in ms being sent to statsd with
the following metric name:::

  my.prefix.requests.somehost-com.POST.200


Session lifecycle
-----------------

We found many of our services were not using session object properly, often
creating/destroying them per request, thus not benefiting from the default
connection pooling provided by requests. This especially painful for latency
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

If you wish to use a custom subclass of Session rather than the default
requests.Session, just pass the session class as an argument. Talisker will
ensure there is one instance of this session subclass per thread.::

  session = talisker.requests.get_session(MyCustomSessionClass)

This works because talisker does not subclass Session to add metrics or
requests id tracing. Instead, it adds a response hook to the session object for
metrics, and decorates the prepare_request *instance* method to inject the header
(ugh, but I couldn't find a better way).

If you wish to use taliskers enhancements, but not the lifecycle management, you can do::

  session = MySession()
  talisker.requests.configure(session)

and session will now have metrics and id tracing.

