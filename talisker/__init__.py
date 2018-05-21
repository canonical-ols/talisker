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
from talisker.util import ensure_extra_versions_supported

__version__ = '0.9.9'
__all__ = [
    'initialise',
    'get_config',
    'run',
    'run_gunicorn',
    'run_celery',
    'run_gunicorn_eventlet',
    'run_gunicorn_gevent',
]


def initialise(env=os.environ):
    config = get_config(env)
    import talisker.logs
    talisker.logs.configure(config)
    # now that logging is set up, initialise other modules
    # sentry first, so we can report any further errors in initialisation
    # TODO: add deferred logging, so we can set up sentry first thing
    import talisker.sentry
    talisker.sentry.get_client()
    import talisker.statsd
    talisker.statsd.get_client()
    import talisker.endpoints
    talisker.endpoints.get_networks()
    return config


ACTIVE = set(['true', '1', 'yes', 'on'])
INACTIVE = set(['false', '0', 'no', 'off'])


def get_config(env=os.environ):
    """Load talisker config from environment"""
    devel = env.get('DEVEL', '').lower() in ACTIVE
    color = False
    if devel:
        if 'TALISKER_COLOR' in env:
            color_name = env['TALISKER_COLOR'].lower()
            if color_name in ACTIVE:
                color = 'default'
            elif color_name in INACTIVE:
                color = False
            else:
                color = color_name
        else:
            color = 'default' if sys.stderr.isatty() else False
    # log all queries in devel by default
    default_query_time = '0' if devel else '-1'
    return {
        'devel': devel,
        'color': color,
        'debuglog': env.get('DEBUGLOG'),
        'slowquery_threshold': int(
            env.get('TALISKER_SLOWQUERY_THRESHOLD', default_query_time)),
        'logstatus': env.get('TALISKER_LOGSTATUS', '').lower() in ACTIVE
    }


TALISKER_ENV_VARS = {
    # development
    'DEVEL',
    'DEBUGLOG',
    'TALISKER_COLOR',
    'TALISKER_LOGSTATUS',
    # sentry config
    'SENTRY_DSN',
    'TALISKER_DOMAIN',
    'TALISKER_ENV',
    'TALISKER_UNIT',
    # production
    'STATSD_DSN',
    'TALISKER_NETWORKS',
    'TALISKER_SLOWQUERY_THRESHOLD',
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


def run_celery(argv=sys.argv):
    initialise()
    os.environ['CELERYD_REDIRECT_STDOUTS'] = 'False'
    # technically we don't need this, as we disable celery's logging
    # altogether, but it doesn't hurt
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = 'False'
    ensure_extra_versions_supported('celery')
    import talisker.celery
    from celery.bin.celery import main
    talisker.celery.enable_signals()
    main(argv)


def run_gunicorn():
    config = initialise()
    import talisker.celery
    import talisker.gunicorn
    talisker.celery.enable_signals()
    app = talisker.gunicorn.TaliskerApplication(
        "%(prog)s [OPTIONS] [APP_MODULE]", config['devel'], config['debuglog'])
    return app.run()


# these two entrypoints workaround a bug in requests on python 3.6 for tls
# https://github.com/requests/requests/issues/3752
# they may go away once requests fixes this issue
def run_gunicorn_eventlet():
    # this is taken from gunicorn EventletWorker.patch()
    import eventlet
    eventlet.monkey_patch(os=False)
    run_gunicorn()


def run_gunicorn_gevent():
    import gevent
    # this is taken from gunicorn GeventWorker.patch()
    from gevent import monkey
    if gevent.version_info[0] == 0:
        monkey.patch_all()
    else:
        monkey.patch_all(subprocess=True)
    run_gunicorn()
