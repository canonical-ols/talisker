#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from collections import deque
import logging
import sys

from gunicorn.glogging import Logger
from gunicorn.app.wsgiapp import WSGIApplication

import talisker
import talisker.logs
import talisker.sentry
import talisker.statsd
import talisker.metrics
import talisker.wsgi


__all__ = [
    'TaliskerApplication',
]

# settings for gunicorn when in development
DEVEL_SETTINGS = {
    'timeout': 99999,
    'reload': True,
}


logger = logging.getLogger(__name__)


# We add a synthetic signal, SIGCUSTOM, to gunicorn's known signals. This
# allows us to get gunicorn to process the effects of this signal in the
# arbiter's main loop, rather than within the limited context of the signal
# handlers.  This makes worker clean up serialized and normal python code.

DEAD_WORKERS = deque()  # storage for recording dead pids


def handle_custom():
    """Handler for a fake 'signal', to be called from the arbiter's main loop.

    This performs the aggregation of prometheus metrics files for dead workers,
    in a serialized and safe manner.
    """
    from talisker.prometheus import prometheus_cleanup_worker
    pid = None
    while DEAD_WORKERS:
        try:
            pid = DEAD_WORKERS.popleft()
            logger.info('cleaning up prometheus metrics', extra={'pid': pid})
            prometheus_cleanup_worker(pid)
        except Exception:
            # we should never fail at cleaning up
            logger.exception(
                'failed to cleanup prometheus worker files',
                extra={'pid': pid},
            )
    # Clear any sentry breadcrumbs that might have built up
    # This is not ideal, but it's the only place the master process calls our
    # code, so...
    # If we don't, breadcrumbs keep on collecting forever.
    talisker.clear_context()


def gunicorn_on_starting(arbiter):
    """Gunicorn on_starting server hook.

    Sets up the fake signal and handler on the arbiter instance.
    """
    arbiter.SIG_NAMES['SIGCUSTOM'] = 'custom'
    arbiter.handle_custom = handle_custom


def gunicorn_child_exit(server, worker):
    """Gunicorn child_exit server hook.

    Note: this runs in a signal handler context, and thus cannot safely perform
    IO, so no logging :(
    """
    DEAD_WORKERS.append(worker.pid)
    # queue the fake signal for processing
    if 'SIGCUSTOM' not in server.SIG_QUEUE:
        server.SIG_QUEUE.append('SIGCUSTOM')


def gunicorn_worker_abort(worker):
    """Worker SIGABRT handler function.

    SIGABRT is only used by gunicorn on worker timeout. We raise a custom
    exception, rather than falling through to the default of SystemExit, which
    is easier to catch and handle as a normal error by our WSGI middleware.
    """
    raise talisker.wsgi.RequestTimeout(
        'gunicorn worker timeout (pid: {})'.format(worker.pid)
    )


def gunicorn_worker_exit(server, worker):
    """Worker exit function.

    Last chance to try log any outstanding requests before we die.
    """
    for rid in list(talisker.wsgi.REQUESTS):
        request = talisker.wsgi.REQUESTS[rid]
        try:
            raise talisker.wsgi.RequestTimeout(
                'finish processing ongoing requests on worker exit '
                '(pid: {})'.format(worker.pid)
            )
        except talisker.wsgi.RequestTimeout:
            request.exc_info = sys.exc_info()
            request.finish_request(timeout=True)


class GunicornLogger(Logger):
    """Custom gunicorn logger to undo gunicorns error log config."""

    def setup(self, cfg):
        super(GunicornLogger, self).setup(cfg)
        # remove the default error handler, instead let it filter up to root
        self.error_log.propagate = True
        self._set_handler(self.error_log, None, None)


class TaliskerApplication(WSGIApplication):
    def __init__(self, prog, devel=False, debuglog=False):
        self._devel = devel
        self._debuglog = debuglog
        super(TaliskerApplication, self).__init__(prog)

    def load_wsgiapp(self):
        """Automatically wrap the provided WSGI app"""
        app = super(TaliskerApplication, self).load_wsgiapp()
        app = talisker.wsgi.wrap(app)
        return app

    def init(self, parser, opts, args):
        """Provide talisker specific default config for gunicorn.

        These are just defaults, and can be overridden in cli/config,
        but it is helpful to set them here.
        """
        cfg = super(TaliskerApplication, self).init(parser, opts, args)
        if cfg is None:
            cfg = {}

        cfg['logger_class'] = GunicornLogger
        cfg['worker_exit'] = gunicorn_worker_exit
        cfg['worker_abort'] = gunicorn_worker_abort

        # only enable these if we are doing multiproc cleanup
        if talisker.prometheus_multiproc_cleanup:
            cfg['on_starting'] = gunicorn_on_starting
            cfg['child_exit'] = gunicorn_child_exit

        # development config
        if self._devel:
            logger = logging.getLogger(__name__)
            logger.debug(
                'devel mode: setting gunicorn devel default config',
                extra=DEVEL_SETTINGS)
            cfg.update(DEVEL_SETTINGS)

        return cfg

    def load_config(self):
        super(TaliskerApplication, self).load_config()

        logger = logging.getLogger(__name__)
        # override and warn

        if self.cfg.errorlog != '-':
            logger.warning(
                'ignoring gunicorn errorlog config, talisker logs to stderr',
                extra={'errorlog': self.cfg.errorlog})
            self.cfg.set('errorlog', '-')

        if self.cfg.loglevel.lower() == 'debug' and self._devel:
            # user has configured debug level logging
            self.cfg.set('loglevel', 'DEBUG')
            talisker.logs.enable_debug_log_stderr()

        # ensure gunicorn sends debug level messages when needed
        if self._debuglog:
            self.cfg.set('loglevel', 'DEBUG')

        # override and warn
        if self.cfg.statsd_host or self.cfg.statsd_prefix:
            logger.warning(
                'ignoring gunicorn statsd config, as has no effect when '
                'using talisker, as it uses STATS_DSN env var',
                extra={'statsd_host': self.cfg.statsd_host,
                       'statsd_prefix': self.cfg.statsd_prefix})
            self.cfg.set('statsd_host', None)
            self.cfg.set('statsd_prefix', None)

        # trust but warn
        if self.cfg.logger_class is not GunicornLogger:
            logger.warning(
                'using custom gunicorn logger class - this may break '
                'Talisker\'s logging configuration',
                extra={'logger_class': self.cfg.logger_class})
