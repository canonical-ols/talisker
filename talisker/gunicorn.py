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
    'accesslog': '-',
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
    talisker.clear_contexts()


def gunicorn_on_starting(arbiter):
    """Gunicorn on_starging server hook.

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


def gunicorn_pre_request(worker, req):
    """Gunicorn pre_request hook.

    Clear any previous contexts on new request.

    Note: we do this on way in, rather than the way out, to preserve the
    request_id context when there's a timeout.
    """
    talisker.clear_contexts()


class GunicornLogger(Logger):
    """Custom gunicorn logger to use structured logging."""

    def get_response_status(self, resp):
        """Resolve differences in status encoding.

        This can vary based on gunicorn version and worker class."""
        if hasattr(resp, 'status_code'):
            return resp.status_code
        elif isinstance(resp.status, str):
            return int(resp.status[:3])
        else:
            return resp.status

    def access(self, resp, req, environ, request_time):
        if not (self.cfg.accesslog or self.cfg.logconfig or self.cfg.syslog):
            return

        status_url = environ.get('PATH_INFO', '').startswith('/_status/')

        if status_url and not talisker.get_config().logstatus:
            return

        status = self.get_response_status(resp)
        msg, extra = talisker.wsgi.get_metadata(
            environ,
            status,
            resp.headers,
            request_time.total_seconds(),
            resp.sent,
        )

        try:
            self.access_log.info(msg, extra=extra)
        except Exception:
            self.exception()

        if not status_url:
            labels = {
                'view': extra.get('view', 'unknown'),
                'method': extra['method'],
                'status': str(status),
            }

            talisker.wsgi.WSGIMetric.count.inc(**labels)
            if status >= 500:
                talisker.wsgi.WSGIMetric.errors.inc(**labels)
            talisker.wsgi.WSGIMetric.latency.observe(
                extra['duration_ms'], **labels)

    def setup(self, cfg):
        super(GunicornLogger, self).setup(cfg)
        # remove the default error handler, instead let it filter up to root
        self.error_log.propagate = True
        self._set_handler(self.error_log, None, None)
        if cfg.accesslog is not None:
            if cfg.accesslog == '-':
                # just propagate to our root logger
                self.access_log.propagate = True
                self._set_handler(self.access_log, None, None)
            else:
                self._set_handler(
                    self.access_log,
                    cfg.accesslog,
                    fmt=talisker.logs.StructuredFormatter())

    @classmethod
    def install(cls):
        # in case used as a library, rather than via the entrypoint,
        # install the logger globally, as this is the earliest point we can do
        # so, if not using the talisker entry point
        logging.setLoggerClass(talisker.logs.StructuredLogger)


class TaliskerApplication(WSGIApplication):
    def __init__(self, prog, devel=False, debuglog=False):
        self._devel = devel
        self._debuglog = debuglog
        super(TaliskerApplication, self).__init__(prog)

    def load_wsgiapp(self):
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
        cfg['pre_request'] = gunicorn_pre_request

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
