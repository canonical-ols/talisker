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

from gunicorn.instrument import statsd as gstatsd
from gunicorn.config import AccessLogFormat
from gunicorn.app.wsgiapp import WSGIApplication

from . import logs
from . import wsgi
from . import statsd


__all__ = ['access_log_format', 'logger_class']


class GunicornLogger(gstatsd.Statsd):
    """Custom gunicorn logger to use structured logging.

    Based on the statsd gunicorn logger, and also increases timestamp
    resolution to include msec in access and error logs.
    """

    # for access log
    def now(self):
        """return date in Apache Common Log Format, but with milliseconds"""
        formatted = datetime.utcnow().strftime('%d/%b/%Y:%H:%M:%S.%f')
        # trim to milliseconds, and hardcode TMZ, for standardising
        return '[' + formatted[:-3] + ' +0000]'

    def setup(self, cfg):
        super(GunicornLogger, self).setup(cfg)
        # gunicorn doesn't allow formatter customisation, so we need to alter
        # after setup
        error_handler = self._get_gunicorn_handler(self.error_log)
        error_handler.setFormatter(logs.StructuredFormatter())
        access_handler = self._get_gunicorn_handler(self.access_log)
        if access_handler:
            access_handler.setFormatter(
                logs.StructuredFormatter(self.access_fmt))

    @classmethod
    def install(cls):
        # in case used as a library, rather than via the entrypoint,
        # install the logger globally, as this is the earliest point we can do
        # so, if not using the talisker entry point
        logging.setLoggerClass(logs.StructuredLogger)


# gunicorn config
access_log_format = AccessLogFormat.default + ' duration=%(D)s'


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

        cfg.update({
            'logger_class': GunicornLogger,
            'access_log_format': access_log_format,
            # level filtering controlled by handler, not logger
            'loglevel': 'notset'
        })

        # wire up statsd, if configured
        config = statsd.get_config()
        if 'hostport' in config and 'prefix' in config:
            cfg['statsd_host'] = config['hostport']
            cfg['statsd_prefix'] = config['prefix']

        # development config
        if self._devel:
            cfg['accesslog'] = '-'
            cfg['timeout'] = 99999

        return cfg


def parse_environ(environ):
    devel = 'DEVEL' in environ
    debug_log = environ.get('DEBUGLOG')
    return devel, debug_log


def run():  # pragma: no cover
    devel, debug = parse_environ(os.environ)
    logs.configure(devel, debug)
    app = TaliskerApplication(
        "%(prog)s [OPTIONS] [APP_MODULE]", devel)
    return app.run()


if __name__ == '__main__':
    run()  # pragma: no cover
