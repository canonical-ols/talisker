import logging

import celery
import talisker.celery
from talisker import request_id

def test_logging(log):

    app = celery.Celery()
    app.conf.update(CELERY_ALWAYS_EAGER=True)
    logger = logging.getLogger(__name__)

    @app.task
    @talisker.celery.logging
    def foo(a):
        logger.info('test')

    with request_id.context('id'):
        talisker.celery.delay(foo, 1).get()
    tags = log[0]._structured
    assert tags['request_id'] == 'id'
    assert len(tags['task_id']) == 36  # uuid

