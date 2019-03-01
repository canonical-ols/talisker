.. highlight:: python



==================
Request Id Tracing
==================

A request id is used for log tracing. Talisker will use a request id
provided in an request's X-Request-Id header, or generate one if needed.

For that request, talisker will then:

  * add in all log messages generated during that request
  * add it as a *response* header
  * include in outgoing HTTP requests using talisker requests Session
  * in the WSGI environ ('REQUEST_ID')
  * in the raven error data

This is implemented using werkzeug.locals, to provide thread/greenlet
local storage.


Non-http Id Tracing
-------------------

For other uses, you can use the following methods to inject a request id
in logging messages::

    def get_id(arg, *args, **kwargs):
        return arg.request_id

    @request_id.decorator(get_id)
    def my_task(arg, any, other='stuff'):
        ...
        log.info('interesting thing')

Or::

    def my_task(arg, any, other='stuff'):
        with request_id.context(arg.request_id):
            ...
            log.info('interesting thing')

This is useful for background tasks like celery.
