import functools

from talisker import logs, request_id


def logging(func):
    """Add celery specific logging context."""
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        from celery import current_task
        tags = {'task_id': current_task.request.id}
        if 'request_id' in kwargs:
            tags['request_id'] = kwargs.pop('request_id')
        with logs.extra_logging(extra=tags):
            return func(*args, **kwargs)

    return decorator


def delay(task, *args, **kwargs):
    id = request_id.get()
    if id:
        kwargs['request_id'] = id
    return task.delay(*args, **kwargs)


def run():
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = False
    from celery.__main__ import main
    logs.configure()
    main()
