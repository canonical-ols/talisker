from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from collections import OrderedDict
import logging

import pytest

from talisker.context import context
from talisker import logs


@pytest.yield_fixture(autouse=True)
def clean_up_context():
    yield
    context.__release_local__()
    logs.StructuredLogger._extra = OrderedDict()
    logs.StructuredLogger._prefix = ''
    logs._logging_configured = []
    logging.getLogger().handlers = []
