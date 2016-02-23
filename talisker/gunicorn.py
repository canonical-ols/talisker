from __future__ import absolute_import, division, print_function
from datetime import datetime
import logging
import sys

from gunicorn.instrument import statsd
from gunicorn.config import AccessLogFormat
from gunicorn.app.wsgiapp import WSGIApplication

import talisker.logs
from talisker.wsgi import wsgi_wrap


__all__ = ['access_log_format', 'logger_class']


class GunicornLogger(statsd.Statsd):
    """Custom gunicorn logger to use striuctured logging.

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
        error_handler.setFormatter(talisker.logs.StructuredFormatter())
        access_handler = self._get_gunicorn_handler(self.access_log)
        if access_handler:
            access_handler.setFormatter(
                talisker.logs.StructuredFormatter(self.access_fmt))

    @classmethod
    def install(cls):
        logging.setLoggerClass(talisker.logs.StructuredLogger)


# gunicorn config
access_log_format = AccessLogFormat.default + ' duration=%(D)s'
logger_class = GunicornLogger


class TaliskerApplication(WSGIApplication):
    def load_wsgiapp(self):
        app = super(TaliskerApplication, self).load_wsgiapp()
        app = wsgi_wrap(app)
        return app


def run():
    import argparse
    from gunicorn.config import Config
    gunicorn_parser = Config('%(prog)s [OPTIONS] [APP_MODULE]').parser()
    p = argparse.ArgumentParser(
        usage='%(prog)s NAME [--devel] -- [GUNICORN ARGS ..]',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='A runner for gunicorn to configure talisker logging',
        epilog=('All other arguments are as for gunicorn:\n\n' +
                gunicorn_parser.format_help()),
    )
    p.add_argument('name', help='name of service for log message (required)')
    p.add_argument('--devel', action='store_true',
                   help='enable extra development logging')
    p.add_argument('gunicorn', nargs='+',
                   help='gunicorn arguments (use -- to separate)')
    args = p.parse_args()

    talisker.logs.configure_logging(
        args.name, devel=args.devel)

    # hardcode talisker values
    cli_args = [
        '--access-logformat', access_log_format,
        '--logger-class', 'talisker.gunicorn.GunicornLogger',
    ]
    # fix up argv to be what gunicorn expects
    # this is not great, but gunicorn's extensibility is limited
    sys.argv = sys.argv[0:1] + cli_args + args.gunicorn

    return TaliskerApplication(
        "%(prog)s [NAME] [DEBUG] -- [OPTIONS] [APP_MODULE]").run()

if __name__ == '__main__':
    run()
