# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

__author__ = 'Simon Davy'
__email__ = 'simon.davy@canonical.com'
__version__ = '0.1.0'
__all__ = ['signal_restart', 'set_version']

from talisker.endpoints import (
    signal_restart,
    set_version,
)
