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
import logging
import sys
import os

from future.utils import exec_

__author__ = 'Simon Davy'
__email__ = 'simon.davy@canonical.com'
__version__ = '0.9.1'


__all__ = ['initialise', 'get_config', 'run']


def initialise(env=os.environ):
    config = get_config(env)
    # deferred import so the metadata can be used
    import talisker.logs
    talisker.logs.configure(config)
    # now that logging is set up, initialise other modules
    import talisker.statsd
    talisker.statsd.get_client()
    import talisker.endpoints
    talisker.endpoints.get_networks()
    return config


def get_config(env=os.environ):
    """Load talisker config from environment"""
    return {
        'debuglog': env.get('DEBUGLOG'),
        'devel': sys.stderr.isatty() or 'DEVEL' in env,
    }


class RunException(Exception):
    pass


def run():
    """Initialise Talisker then exec python script."""
    initialise()
    logger = logging.getLogger('talisker.run')

    name = sys.argv[0]
    if '__main__.py' in name:
        # friendlier message
        name = '{} -m talisker'.format(sys.executable)

    extra = {}
    try:
        if len(sys.argv) < 2:
            raise RunException('usage: {} <script>  ...'.format(name))

        script = sys.argv[1]
        extra['script'] = script
        with open(script, 'rb') as f:
            code = compile(f.read(), script, 'exec')

        # pretend we just invoked python script.py by mimicing usual python
        # behavior
        sys.path.insert(0, os.path.dirname(script))
        sys.argv = sys.argv[1:]
        globs = {}
        globs['__file__'] = script
        globs['__name__'] = '__main__'
        globs['__package__'] = None

        exec_(code, globs, None)

    except Exception:
        logger.exception('Unhandled exception', extra=extra)
        sys.exit(1)
