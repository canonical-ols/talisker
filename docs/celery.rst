.. highlight:: python


======
Celery
======

Talisker provides some optional integration with celery.

If you use talisker's celery wrapper, then celery will use the talisker
logging configuration. In addition, if statsd is configured, then
Talisker will enable basic celery task metrics by default:

.. code-block:: bash

   $ talisker.celery worker -A myapp

Talisker sets up statsd timers for

  - celery.<task_name>.enqueue  (time to publish to queue)
  - celery.<task_name>.run      (time to run task)

And statsd counters for

  - celery.<task_name>.retry
  - celery.<task_name>.success
  - celery.<task_name>.failure
  - celery.<task_name>.revoked

Note: talisker supports celery>=3.1.0. If you need to be sure, the
package supports extras args to install celery dependencies:

.. code-block:: bash

   $ pip install talisker[celery]
