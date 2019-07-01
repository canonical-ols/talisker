================
Request Timeouts
================

Talisker supports the idea of a request deadline, with the goal of
failing early, especially when under load. This deadline can be
specified as a timeout, either globaly or per-endpoint.

Talisker will try to use the remaining time left until the deadline as
network timeout parameters. It supports HTTP and SQL requests out of the
box, if you use `talisker.requests.TaliskerAdapter` and
`talisker.postgresql.TaliskerConnecton`, respectivley. It also provides
an API to get the remaining time left before the deadline, which you can
use in other network operations.

.. code-block:: python

    timeout = Context.deadline_timeout()

Note: this will raise `talisker.DeadlineExceeded` if the deadline has
been exceeded.

Talisker timeouts are not hard guarantees - Talisker will not cancel
your request. They merely try to ensure that network operations will
fail earlier rather than blocking for long periods.

Deadline Propagation
--------------------

The deadline can be set via a the X-Request-Deadline request header, as
an ISO 8601 datestring.  This will override the configured endpoint
deadline, if any. Talisker's requests support will also send the current
deadline as a header in any outgoing requests. This allows API gateway
services to communicate top-level request deadlines ina calls to other
services.


Configuring Timeouts
--------------------

You can set a global timeout via the TALISKER_REQUEST_TIMEOUT config, or
per endpoint with the `talisker.request_timeout` decorator.

.. code-block:: python

    @talisker.request_timeout(3000)  # milliseconds
    def view(request):
        ...


Soft Timeouts
-------------

Talisker supports the concept of a `soft_timeout`, which will
send a sentry report if a request takes longer than the soft timeout
threshold. This is useful to provide richer information for problematic
requests.

You can set this global via the TALISKER_SOFT_REQUEST_TIMEOUT
config or per endpoint via the `talisker.request_timeout` decorator.

.. code-block:: python

    @talisker.request_timeout(soft_timeout=3000)  # milliseconds
    def view(request):
        ...
