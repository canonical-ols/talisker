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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import logging
import os
import tempfile
import sys
from collections import OrderedDict

from gunicorn.instrument import statsd as gstatsd
from gunicorn.app.wsgiapp import WSGIApplication

from . import logs
from . import statsd
from . import util
from . import wsgi
import talisker.celery


__all__ = [
    'run',
]

# settings for gunicorn when in development
DEVEL_SETTINGS = {
    'accesslog': '-',
    'timeout': 99999,
    'reload': True,
}


def prometheus_multiprocess_worker_exit(server, worker):
    """Default worker cleanup function for multiprocess prometheus_client."""
    if 'prometheus_multiproc_dir' in os.environ:
        logging.getLogger(__name__).info(
            'Performing multiprocess prometheus_client cleanup')
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(worker.pid)


class GunicornLogger(gstatsd.Statsd):
    """Custom gunicorn logger to use structured logging.

    Based on the statsd gunicorn logger, and also increases timestamp
    resolution to include msec in access and error logs.
    """
    def __init__(self, cfg):
        super(GunicornLogger, self).__init__(cfg)
        if self.sock is not None:
            self.sock.close()

    def get_extra(self, resp, req, environ, request_time):

        msg = "%s %s" % (environ['REQUEST_METHOD'], environ['RAW_URI'])

        status = resp.status
        if isinstance(status, (str, bytes)):
            status = status[:3]

        extra = OrderedDict()
        extra['method'] = environ.get('REQUEST_METHOD')
        extra['path'] = environ.get('PATH_INFO')
        extra['qs'] = environ.get('QUERY_STRING')
        extra['status'] = status
        extra['ip'] = environ.get('REMOTE_ADDR', None)
        extra['proto'] = environ.get('SERVER_PROTOCOL')
        extra['length'] = getattr(resp, 'sent', None)
        extra['referrer'] = environ.get('HTTP_REFERER', None)
        extra['ua'] = environ.get('HTTP_USER_AGENT', None)
        extra['duration'] = (
            request_time.seconds * 1000 +
            float(request_time.microseconds) / 1000
        )

        # the wsgi context has finished by now, so the request_id is no longer
        # set. Instead, we add it explicitly
        headers = dict((k.lower(), v) for k, v in resp.headers)
        request_id = headers.get('x-request-id')
        if request_id:
            extra['request_id'] = request_id

        return msg, extra

    def access(self, resp, req, environ, request_time):
        if not (self.cfg.accesslog or self.cfg.logconfig or self.cfg.syslog):
            return

        msg, extra = self.get_extra(resp, req, environ, request_time)

        try:
            self.access_log.info(msg, extra=extra)
        except:
            self.exception()

        # due to the fact we do access logs differently, we have to duplicate
        # this here :(
        duration_in_ms = (
            request_time.seconds * 1000 +
            float(request_time.microseconds) / 10 ** 3
        )
        status = resp.status
        if isinstance(status, str):
            status = int(status.split(None, 1)[0])
        self.histogram("gunicorn.request.duration", duration_in_ms)
        self.increment("gunicorn.requests", 1)
        self.increment("gunicorn.request.status.%d" % status, 1)

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
                    fmt=logs.StructuredFormatter())

    @classmethod
    def install(cls):
        # in case used as a library, rather than via the entrypoint,
        # install the logger globally, as this is the earliest point we can do
        # so, if not using the talisker entry point
        logging.setLoggerClass(logs.StructuredLogger)

    def gauge(self, name, value):
        statsd.get_client().gauge(name, value)

    def increment(self, name, value, sampling_rate=1.0):
        statsd.get_client().incr(name, value, rate=sampling_rate)

    def decrement(self, name, value, sampling_rate=1.0):
        statsd.get_client().decr(name, value, rate=sampling_rate)

    def histogram(self, name, value):
        statsd.get_client().timing(name, value)


class TaliskerApplication(WSGIApplication):
    def __init__(self, prog, devel=False, debuglog=False):
        self._devel = devel
        self._debuglog = debuglog
        super(TaliskerApplication, self).__init__(prog)

    def load_wsgiapp(self):
        app = super(TaliskerApplication, self).load_wsgiapp()
        app = wsgi.wrap(app)
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

        # Use pip to find out if prometheus_client is available, as
        # importing it here would break multiprocess metrics
        if util.pkg_is_installed('prometheus-client'):
            cfg['worker_exit'] = prometheus_multiprocess_worker_exit

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
            logger.warn(
                'ignoring gunicorn errorlog config, talisker logs to stderr',
                extra={'errorlog': self.cfg.errorlog})
            self.cfg.set('errorlog', '-')

        if self.cfg.loglevel.lower() == 'debug':
            # user has configured debug level logging
            self.cfg.set('loglevel', 'DEBUG')
            # only echo to stderr if we are in interactive mode
            if sys.stderr.isatty():
                logs.enable_debug_log_stderr()

        # ensure gunicorn sends debug level messages when needed
        if self._debuglog:
            self.cfg.set('loglevel', 'DEBUG')

        # override and warn
        if self.cfg.statsd_host or self.cfg.statsd_prefix:
            logger.warn(
                'ignoring gunicorn statsd config, as has no effect when '
                'using talisker, as it uses STATS_DSN env var',
                extra={'statsd_host': self.cfg.statsd_host,
                       'statsd_prefix': self.cfg.statsd_prefix})
            self.cfg.set('statsd_host', None)
            self.cfg.set('statsd_prefix', None)

        # trust but warn
        if self.cfg.logger_class is not GunicornLogger:
            logger.warn(
                'using custom gunicorn logger class - this may break '
                'Talisker\'s logging configuration',
                extra={'logger_class': self.cfg.logger_class})
        # Use pip to find out if prometheus_client is available, as
        # importing it here would break multiprocess metrics
        if (util.pkg_is_installed('prometheus-client') and
                (self.cfg.workers or 1) > 1):
            if 'prometheus_multiproc_dir' not in os.environ:
                logger.info('running in multiprocess mode but '
                            '`prometheus_multiproc_dir` envvar not set')
                tmpdir = tempfile.mkdtemp()
                os.environ['prometheus_multiproc_dir'] = tmpdir

            logger.info('using `%s` for multiprocess prometheus metrics',
                        os.environ['prometheus_multiproc_dir'])


def run():
    config = talisker.initialise()
    talisker.celery.enable_signals()
    app = TaliskerApplication(
        "%(prog)s [OPTIONS] [APP_MODULE]", config['devel'], config['debuglog'])
    return app.run()
