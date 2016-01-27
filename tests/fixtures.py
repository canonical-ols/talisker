import logging

import pytest

from talisker.context import context
from talisker import logs


@pytest.yield_fixture(autouse=True)
def clean_up_context():
    yield
    context.__release_local__()
    logs.StructuredLogger._extra = {}
    logs.StructuredLogger._prefix = ''
    logs._logging_configured = []
    logging.getLogger().handlers = []
