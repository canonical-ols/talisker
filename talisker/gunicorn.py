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

from collections import OrderedDict
import logging
import os
import tempfile

from gunicorn.glogging import Logger
from gunicorn.app.wsgiapp import WSGIApplication

import talisker
import talisker.logs
import talisker.statsd
import talisker.metrics
from talisker.util import pkg_is_installed
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


class GunicornMetric:
    latency = talisker.metrics.Histogram(
        name='gunicorn_latency',
        documentation='Duration of requests served by Gunicorn',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )

    count = talisker.metrics.Counter(
        name='gunicorn_count',
        documentation='Count of gunicorn requests',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )

    errors = talisker.metrics.Counter(
        name='gunicorn_errors',
        documentation='Count of Gunicorn errors',
        labelnames=['view', 'status', 'method'],
        statsd='{name}.{view}.{method}.{status}',
    )


def prometheus_multiprocess_worker_exit(server, worker):
    """Default worker cleanup function for multiprocess prometheus_client."""
    if 'prometheus_multiproc_dir' in os.environ:
        logging.getLogger(__name__).info(
            'Performing multiprocess prometheus_client cleanup')
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(worker.pid)


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

    def get_extra(self, resp, req, environ, request_time, status):
        # the wsgi context has finished by now, so the various bits of relevant
        # information are only in the headers
        headers = dict((k.lower(), v) for k, v in resp.headers)
        extra = OrderedDict()
        extra['method'] = environ.get('REQUEST_METHOD')
        extra['path'] = environ.get('PATH_INFO')
        qs = environ.get('QUERY_STRING')
        if qs is not None:
            extra['qs'] = environ.get('QUERY_STRING')
        extra['status'] = status
        if 'x-view-name' in headers:
            extra['view'] = headers['x-view-name']
        extra['duration_ms'] = (
            request_time.seconds * 1000 +
            float(request_time.microseconds) / 1000
        )
        extra['ip'] = environ.get('REMOTE_ADDR', None)
        extra['proto'] = environ.get('SERVER_PROTOCOL')
        extra['length'] = getattr(resp, 'sent', None)
        if 'CONTENT_LENGTH' in environ:
            try:
                extra['request_length'] = int(environ['CONTENT_LENGTH'])
            except ValueError:
                pass
        if 'CONTENT_TYPE' in environ:
            extra['request_type'] = environ['CONTENT_TYPE']
        referrer = environ.get('HTTP_REFERER', None)
        if referrer is not None:
            extra['referrer'] = environ.get('HTTP_REFERER', None)
        if 'HTTP_X_FORWARDED_FOR' in environ:
            extra['forwarded'] = environ['HTTP_X_FORWARDED_FOR']
        extra['ua'] = environ.get('HTTP_USER_AGENT', None)

        request_id = headers.get('x-request-id')
        if request_id:
            extra['request_id'] = request_id

        msg = "{method} {path}{0}".format('?' if extra['qs'] else '', **extra)
        return msg, extra

    def access(self, resp, req, environ, request_time):
        if not (self.cfg.accesslog or self.cfg.logconfig or self.cfg.syslog):
            return

        status_url = environ.get('PATH_INFO', '').startswith('/_status/')

        if status_url and not talisker.get_config()['logstatus']:
            return

        status = self.get_response_status(resp)
        msg, extra = self.get_extra(resp, req, environ, request_time, status)

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

            GunicornMetric.count.inc(**labels)
            if status >= 500:
                GunicornMetric.errors.inc(**labels)
            GunicornMetric.latency.observe(
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

        # Use pip to find out if prometheus_client is available, as
        # importing it here would break multiprocess metrics
        if pkg_is_installed('prometheus-client'):
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
        # Use pip to find out if prometheus_client is available, as
        # importing it here would break multiprocess metrics
        if (pkg_is_installed('prometheus-client') and
                (self.cfg.workers or 1) > 1):
            if 'prometheus_multiproc_dir' not in os.environ:
                logger.info('running in multiprocess mode but '
                            '`prometheus_multiproc_dir` envvar not set')
                tmpdir = tempfile.mkdtemp()
                os.environ['prometheus_multiproc_dir'] = tmpdir

            logger.info('using `%s` for multiprocess prometheus metrics',
                        os.environ['prometheus_multiproc_dir'])
