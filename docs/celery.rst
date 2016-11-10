.. highlight:: python


======
Celery
======

Talisker provides some optional integration with celery.

If you use taliskers celery wrapper, then celery will use talisker
logging configuration.  In addition, if statsd is configured, then
talisker will enable basic celery task metrics by default::

   $ talisker.celery worker -A myapp

Note: talisker supports celery>=3.1.0. If you need to be sure, the
package supports extras args to install celery dependencies::

   $ pip install talisker[celery]
