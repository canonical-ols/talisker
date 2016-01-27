import logging

import pytest

from talisker.context import context
from talisker import logging as tlog


@pytest.yield_fixture(autouse=True)
def clean_up_context():
    yield
    context.__release_local__()
    tlog.StructuredLogger._extra = {}
    tlog.StructuredLogger._prefix = ''
    tlog._logging_configured = []
    logging.getLogger().handlers = []
