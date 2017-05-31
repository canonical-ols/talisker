
.. highlight:: python


========
Gunicorn
========


Basic Usage
-----------

Gunicorn is wsgi server used by Talisker. To use it, simply use the Talisker
wrapper in place of regular gunicorn script.

.. code-block:: bash

    $ talisker.gunicorn -c config.py myapp:wsgi_app

This wrapper simply initialises Talisker before passing control to Gunicorn's
entrypoint. As such, it takes exactly the same command line arguments, and
behaves in the same way.

Talisker supports the sync, gevent, and eventlet workers. Others workers may
work, but have not been tested.  The only place it matters is in the
context-local storage of Talsiker log tags and request ids.  Talisker will use
greenlet based contexts if it finds itself running in a greenlet context, or
else a thread local object.



Python 3.6, Async and Requests
------------------------------

Due to changes in the SSL api in python 3.6, requests currently has a bug with
https endpoints in monkeypatched async context. The details are at
`<https://github.com/requests/requests/issues/3752>`_, but basically the
monkeypatching must be done *before* requests is imported.  Normally, this
would not affect gunicorn, as your app would only import requests in worker
a process after the monkeypatch has been applied. However, because talisker
enables some integrations in the main process, before the gunicorn code is run,
it triggers this bug. Specfically, we import the raven library to get early
error handling, and raven imports requests.

We provide two special entrypoints to work around this problem, if you are
using python 3.6 and eventlet or gevent workers with the requests library.
They simply apply the appropriate monkeypatching first, before then just
initialising talikser and running gunicorn as normal.

.. code-block:: bash

    $ talisker.gunicorn.eventlet --worker-class eventlet -c config.py myapp:wsgi_app

.. code-block:: bash

    $ talisker.gunicorn.gevent --worker-class gevent -c config.py myapp:wsgi_app

