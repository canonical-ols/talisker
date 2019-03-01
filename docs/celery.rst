.. highlight:: python


======
Celery
======

Talisker provides some optional integration with celery. If your project does
not have celery installed, this will not be used.

To run a Celery worker with Talisker, use the provided Celery entrypoint:

.. code-block:: bash

   $ talisker.celery worker -A myapp


Logging
-------

Talisker configures Celery logging to use Talisker's logging mechanisms. It
ensures that the `task_id` and `task_name` will be logged with every log
message for a Celery job.

Additionally, if the job is triggered by a Talisker process (e.g. a Talisker
gunicorn worker) it will add the `request_id` to the logging tags for the
celery job when it executes. This allows you to track tasks initiated by
a specific request id.


Metrics
-------

Talisker will enable basic celery task metrics by default.

Talisker sets up histogram metrics for

  - celery.<task_name>.enqueue  (time to publish to queue)
  - celery.<task_name>.queue    (time in queue)
  - celery.<task_name>.run      (time to run task)

And counters for

  - celery.<task_name>.count    (total tasks)
  - celery.<task_name>.retry    (number of retried tasks)
  - celery.<task_name>.success  (number of successful tasks)
  - celery.<task_name>.failure  (number of failed tasks)
  - celery.<task_name>.revoked  (number of revoked tasks)

Note: talisker supports celery>=3.1.0. If you need to be sure, the
package supports extras args to install celery dependencies:

.. code-block:: bash

   $ pip install talisker[celery]


Sentry
------

Talisker integrates Sentry with Celery, so Celery exceptions will be
reported to Sentry. This uses the standard support in raven for
integrating Celery and Sentry.
