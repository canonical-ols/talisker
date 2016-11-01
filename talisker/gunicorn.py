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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import os
from datetime import datetime
import logging
from collections import OrderedDict

from gunicorn.instrument import statsd as gstatsd
from gunicorn.app.wsgiapp import WSGIApplication

from . import logs
from . import wsgi
from . import statsd
import talisker.celery


__all__ = [
    'logger_class',
    'run',
]

# settings for gunicorn when in development
DEVEL_SETTINGS = {
    'accesslog': '-',
    'timeout': 99999,
}


class GunicornLogger(gstatsd.Statsd):
    """Custom gunicorn logger to use structured logging.

    Based on the statsd gunicorn logger, and also increases timestamp
    resolution to include msec in access and error logs.
    """
    def __init__(self, cfg):
        super(GunicornLogger, self).__init__(cfg)
        if self.sock is not None:
            self.sock.close()
        self.statsd = statsd.get_client()

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

        return msg, extra

    def access(self, resp, req, environ, request_time):
        if not (self.cfg.accesslog or self.cfg.logconfig or self.cfg.syslog):
            return

        msg, extra = self.get_extra(resp, req, environ, request_time)

        try:
            self.access_log.info(msg, extra=extra)
        except:
            self.exception()

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
        self.statsd.gauge(name, value)

    def increment(self, name, value, sampling_rate=1.0):
        self.statsd.incr(name, value, rate=sampling_rate)

    def decrement(self, name, value, sampling_rate=1.0):
        self.statsd.decr(name, value, rate=sampling_rate)

    def histogram(self, name, value):
        self.statsd.timing(name, value)


class TaliskerApplication(WSGIApplication):
    def __init__(self, prog, devel=False):
        self._devel = devel
        super(TaliskerApplication, self).__init__(prog)

    def load_wsgiapp(self):
        app = super(TaliskerApplication, self).load_wsgiapp()
        app = wsgi.wrap(app)
        return app

    def init(self, parser, opts, args):
        """Provide talisker specific default config for gunicorn.

        Default config here can be overriden with cli args or config file."""

        cfg = super(TaliskerApplication, self).init(parser, opts, args)
        if cfg is None:
            cfg = {}

        logger = logging.getLogger(__name__)

        if opts.errorlog is not None and opts.errorlog != '-':
            logger.warn(
                'ignoring gunicorn errorlog config as has no effect when '
                'using talisker, as it logs it to stderr',
                extra={'errorlog': opts.errorlog})

        if opts.statsd_host or opts.statsd_prefix:
            logger.warn(
                'ignoring gunicorn statsd config, as has no effect when '
                'using talisker, as it uses STATS_DSN env var',
                extra={'statsd_host': opts.statsd_host,
                       'statsd_prefix': opts.statsd_prefix})

        cfg.update({
            'logger_class': GunicornLogger,
            # level filtering controlled by handler, not logger
            'loglevel': 'DEBUG',
        })

        # development config
        if self._devel:
            logger.info(
                'setting gunicorn config for development',
                extra=DEVEL_SETTINGS)
            cfg.update(DEVEL_SETTINGS)

        return cfg


def run():
    devel, _ = logs.configure()
    talisker.celery.enable_metrics()
    app = TaliskerApplication(
        "%(prog)s [OPTIONS] [APP_MODULE]", devel)
    return app.run()
