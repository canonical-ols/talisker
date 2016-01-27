#-*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from datetime import datetime
import logging
import socket
import sys

from gunicorn.instrument import statsd
from gunicorn.config import AccessLogFormat

from .context import context


_logging_configured = []


def set_logging_context(**kwargs):
    """Update structured logging keys in a thread/context dict."""
    if not hasattr(context, 'extra'):
        context.extra = {}
    context.extra.update(kwargs)


def init_logging():
    logging.setLoggerClass(StructuredLogger)


def configure_logging(service, level=logging.INFO, devel=False, **kwargs):
    """Configure default logging setup for our services.

    This is basically:
     - log to stderr
     - output hybrid logfmt structured format
     - add some basic structured data by default

    Additionally, we set the 'requests' logger to WARNING.
    """

    # avoid duplicate logging
    if _logging_configured:
        return
    _logging_configured.append(True)

    if 'hostname' not in kwargs:
        kwargs['hostname'] = socket.gethostname()
    kwargs['service'] = service
    # TODO: detect juju unit id?
    # TODO: require revno?

    StructuredLogger.update_extra(kwargs)
    StructuredLogger.set_prefix(service)
    logging.setLoggerClass(StructuredLogger)

    logfmt_formatter = StructuredFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(logfmt_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Silence requests logging, which is created by nova, keystone and swift.
    requests_logger = logging.getLogger('requests')
    requests_logger.setLevel(logging.WARNING)

    # we only want arnings in development, and not structured
    warnings = logging.getLogger('py.warnings')
    warnings.propagate = False

    if devel:
        enable_devel_logging()


def enable_devel_logging():
    # make warnings output to console undecorated
    warning_handler = logging.StreamHandler()
    warning_handler.setFormatter(logging.Formatter('%(message)s'))
    warnings = logging.getLogger('py.warnings')
    while warnings.handlers:
        warnings.removeHandler(warnings.handlers[-1])
    warnings.addHandler(warning_handler)


class StructuredLogger(logging.Logger):
    """A logger that handles passing 'extra' arguments to all logging calls.

    Supports 3 sources of extra structured data:

    1) global extra, designed to be set once at process start/
    2) context extra, designed to be set per request or job, can cleaned up
       afterwards.
    3) per call extra, passed by the log call, as per normal logging
       e.g. log.info('...', extra={...})
       These keys are prefixed by cls._prefix to avoid collisions.

    """

    _extra = {}
    _prefix = ''
    structured = True

    @classmethod
    def update_extra(cls, extra):
        cls._extra.update(**extra)

    @classmethod
    def set_prefix(cls, prefix):
        cls._prefix = prefix.rstrip('.') + '.'

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        # at this point we have 3 possible sources of extra kwargs
        # - global  : cls._extra
        # - context : local.extra
        # - log call: extra
        all_extra = self._extra.copy()
        all_extra.update(getattr(context, 'extra', {}))
        if extra is not None:
            # prefix call site extra args, to avoid collisions
            for k, v in extra.items():
                all_extra[self._prefix + k] = v
        kwargs = dict(func=func, extra=all_extra, sinfo=sinfo)
        if sys.version_info[0] == 2:
            kwargs.pop('sinfo')
        record = super(StructuredLogger, self).makeRecord(
            name, level, fn, lno, msg, args, exc_info, **kwargs)
        # store extra explicitly for StructuredFormatter to use
        if self.structured:
            record._structured = all_extra
        return record


class StructuredFormatter(logging.Formatter):
    """Add additional structured data in logfmt style to format.

    Outputs the specified format as normal, and adds any structured data
    available in logfmt. Requires StructuredLogger to work.

    e.g.

    2016-01-13 10:24:07,357 INFO name "my message" foo=data bar="other data"

    """

    FORMAT = '%(asctime)s %(levelname)s %(name)s "%(message)s"'

    def __init__(self, fmt=None, datefmt=None):
        if fmt is None:
            fmt = StructuredFormatter.FORMAT
        super(StructuredFormatter, self).__init__(fmt, datefmt)

    def getMessage(self):
        msg = super(self, StructuredFormatter).getMessage()
        return self.escape_quotes(msg)

    def format(self, record):
        """Render the format, then add any extra as structured tags."""
        # this is verbatim from the parent class in 2.7
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__

        # add our structured tags *before* exeception info is added
        structured = getattr(record, '_structured', {})
        if structured:
            logfmt = (self.logfmt(k, record.__dict__[k]) for k in structured)
            s += " " + " ".join(logfmt)

        # this is verbatim from the parent class in 2.7
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s = s + "\n"
            try:
                s = s + record.exc_text
            except UnicodeError:
                # Sometimes filenames have non-ASCII chars, which can lead
                # to errors when s is Unicode and record.exc_text is str
                # See issue 8924.
                # We also use replace for when there are multiple
                # encodings, e.g. UTF-8 for the filesystem and latin-1
                # for a script. See issue 13232.
                s = s + record.exc_text.decode(sys.getfilesystemencoding(),
                                               'replace')
        return s

    def escape_quotes(self, s):
        return s.replace('"', r'\"')

    def logfmt(self, k, v):
        if ' ' in v:
            v = '"' + self.escape_quotes(v) + '"'
        return "%s=%s" % (k, v)


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
        error_handler.setFormatter(StructuredFormatter())
        access_handler = self._get_gunicorn_handler(self.access_log)
        access_handler.setFormatter(StructuredFormatter(self.access_fmt))


# gunicorn config
access_log_format = AccessLogFormat.default + ' duration=%(D)s'
logger_class = GunicornLogger
