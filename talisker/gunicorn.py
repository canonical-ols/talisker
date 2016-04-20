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
        logging.setLoggerClass(logs.StructuredLogger)


# gunicorn config
access_log_format = AccessLogFormat.default + ' duration=%(D)s'
logger_class = GunicornLogger


class TaliskerApplication(WSGIApplication):
    def load_wsgiapp(self):
        app = super(TaliskerApplication, self).load_wsgiapp()
        app = wsgi.wrap(app)
        return app

    def init(self, parser, opts, args):
        if opts.access_log_format is None:
            opts.access_log_format = access_log_format
        if opts.logger_class is None:
            opts.logger_class = GunicornLogger
        config = statsd.get_config()
        if 'hostport' in config and opts.statsd_host is None:
            opts.statsd_host = client.hostport
        if 'prefix' in config and opts.statsd_prefix is None:
            opts.statsd_prefix = client.prefix
        super(TaliskerApplication, self).init(parser, opts, args)


def run():
    devel = 'TALISKER_DEVEL' in os.environ
    logs.configure(devel=devel)
    return TaliskerApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()

if __name__ == '__main__':
    run()
