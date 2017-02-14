# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
import sys

from future.utils import exec_

__author__ = 'Simon Davy'
__email__ = 'simon.davy@canonical.com'
__version__ = '0.9.0'


__all__ = ['initialise']


def initialise():
    # deferred import so the metadata can be used
    import talisker.logs
    devel, _ = talisker.logs.configure()
    # now that logging is set up, initialise other modules
    import talisker.statsd
    talisker.statsd.get_client()
    import talisker.endpoints
    talisker.endpoints.get_networks()
    return devel


def run():
    """Initialise Talisker then exec python script."""
    initialise()

    if len(sys.argv) < 2:
        sys.stderr.write('usage: python -m talisker <python script> ...')

    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    with open(script, 'rb') as fp:
        code = compile(fp.read(), script, 'exec')
    globs = {
        '__file__': script,
        '__name__': '__main__',
        '__package__': None,
    }
    return exec_(code, globs, None)
