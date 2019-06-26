===============
Request Context
===============

Talisker uses an implicit context to track requests during execution.
It does this via the contextvars module from the Python standard library
in Python 3.7+, falling back to the contextvars backport from PyPI. It
also includes a minimal backport of ContextVar for use with Python 2.

Talisker creates a new context for each WSGI request or Celery job, and
tracks the request id and other data in that context. Asyncio is
supported, either by the native support in python 3.7, or via the
aiocontextvars package, which you can install by using the asyncio
extra::

    pip install talisker[asyncio]

Note: you need at least python 3.5.3+ to use asyncio with contextvars
- aiocontextvars does not work on earlier versions.

Talisker also explicitly supports contexts when using the Gevent or
Eventlet Gunicorn workers, by swapping the thread local storage out for
the relative greenlet based storage. This support currently does not
work in python 3.7 or above, as it is not possible to switch the
underlying storage.


Request Id
----------

One of the key elements of the context is to track the current request
id. This id can be supplied via a the X-Request-Id header, or else
a uuid4 is used.

This id is automatically attached to all log messages emitted during the
request, as well as the detailed log message talisker emits for the
request itself.

Talisker also support propagating this request id wherever possible.
When using Talisker's requests support, the current request id will be
included in the outgoing request headers. When queuing celery jobs, the
current request id will be passed as a header for that job, and then
used by the job for all log messages when the job runs.

This allows deep tracing of a particular request id across multiple
services boundaries, which is key to debugging complex issues in
distributed systems.


Context API
-----------

Talisker exposes a public API for the current context::

.. highlight:: python

    from talisker import Context

    Context.request_id              # get/set current request id
    Context.clear()                 # clear the current context
    Context.new()                   # create a new context

    # you can also add extras to the current logging context

    Context.logging.push(foo=1)

    # or

    with Context.logging(bar=2):
        ...

