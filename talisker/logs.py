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

from collections import OrderedDict
from contextlib import contextmanager
import time
import logging
import sys
import os

from .request_context import request_context

__all__ = [
    'configure',
    'configure_logging',
    'configure_test_logging',
    'extra_logging',
]

_logging_configured = False


NOISY_LOGS = {
    'requests': logging.WARNING,
}


def set_logging_context(extra=None, **kwargs):
    """Update structured logging keys in a thread/context dict."""
    if not hasattr(request_context, 'extra'):
        request_context.extra = {}
    if extra:
        request_context.extra.update(extra)
    if kwargs:
        request_context.extra.update(kwargs)


@contextmanager
def extra_logging(extra=None, **kwargs):
    set_logging_context(extra, **kwargs)
    yield
    remove = list(kwargs.items())
    if extra:
        remove.extend(extra.items())
    for k, v in remove:
        request_context.extra.pop(k, None)


def add_talisker_handler(level, handler):
    handler.setFormatter(StructuredFormatter())
    handler.setLevel(level)
    handler._talisker_handler = True
    logging.getLogger().addHandler(handler)


def _set_logger_class():
    logging.setLoggerClass(StructuredLogger)
    logging.getLogger().setLevel(logging.NOTSET)


def parse_environ(environ):
    devel = 'DEVEL' in environ
    debug_log = environ.get('DEBUGLOG')
    return devel, debug_log


def configure():  # pragma: no cover
    devel, debug = parse_environ(os.environ)
    configure_logging(devel, debug)
    return devel, debug


def configure_logging(devel=False, debug=None):
    """Configure default logging setup for our services.

    This is basically:
     - log to stderr
     - output hybrid logfmt structured format
     - maybe configure debug logging
    """

    # avoid duplicate logging
    global _logging_configured
    if _logging_configured:
        return

    _set_logger_class()
    # always INFO to stderr
    add_talisker_handler(logging.INFO, logging.StreamHandler())
    configure_warnings(devel)
    supress_noisy_logs()

    # defer this until logging has been set up
    logger = logging.getLogger(__name__)

    if debug is not None:
        if can_write_to_file(debug):
            handler = logging.handlers.TimedRotatingFileHandler(
                debug,
                when='D',
                interval=1,
                backupCount=1,
                delay=True,
                utc=True,
            )
            add_talisker_handler(logging.DEBUG, handler)
            logger.info('enabling debug logs', extra={'path': debug})
        else:
            logger.info('could not enable debug log, could not write to path',
                        extra={'path': debug})

    _logging_configured = True


def can_write_to_file(path):
    try:
        open(path, 'a').close()
    except:
        return False
    else:
        return True


def supress_noisy_logs():
    """Set some custom log levels on some sub logs"""
    for name, level in NOISY_LOGS.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)


def configure_warnings(enable):
    # never propogate warnings to root
    warnings = logging.getLogger('py.warnings')
    warnings.propagate = False

    if enable:
        warnings.addHandler(logging.StreamHandler())


def configure_test_logging():
    """Add a NullHandler to root logger.

    Prevents unconfigured logging from erroring, and swallows all logging,
    which is usually what you want for unit tests.  Unit test fixtures can
    still add their own loggers to assert against log messages if needed.
    """
    _set_logger_class()
    handler = logging.NullHandler()
    add_talisker_handler(logging.NOTSET, handler)
    configure_warnings(True)


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

    _extra = OrderedDict()
    _prefix = 'svc.'
    structured = True

    @classmethod
    def update_extra(cls, extra):
        cls._extra.update(extra)

    # sadly, we must subclass and override, rather that use the new
    # setLogRecordFactory() in 3.2+, as that does not pass the extra args
    # through. Also, we need to support python 2.
    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        # at this point we have 3 possible sources of extra kwargs
        # - log call: extra
        # - context : local.extra
        # - global  : cls._extra
        # These are added in order of most specific to least, to push line
        # noise to the end of the log line
        all_extra = OrderedDict()
        if extra is not None:
            # prefix call site extra args, to avoid collisions
            for k, v in list(extra.items()):
                all_extra[self._prefix + k] = v
        all_extra.update(getattr(request_context, 'extra', {}))
        all_extra.update(
            (k, v) for k, v in self._extra.items() if k not in all_extra)
        kwargs = dict(func=func, extra=all_extra, sinfo=sinfo)
        # python 2 doesn't support sinfo parameter
        if sys.version_info[0] == 2:
            kwargs.pop('sinfo')
        record = super(StructuredLogger, self).makeRecord(
            name, level, fn, lno, msg, args, exc_info, **kwargs)
        # store extra explicitly for StructuredFormatter to use
        if self.structured:
            record._structured = all_extra
        return record


class StructuredFormatter(logging.Formatter):
    """Add additional structured data in logfmt style to formatted log.

    Outputs the specified format as normal, and adds any structured data
    available in logfmt. Requires StructuredLogger to work.

    e.g.

    2016-01-13 10:24:07.357Z INFO name "my message" foo=data bar="other data"

    """

    FORMAT = '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"'
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    # use utc time. No idea why this is not the default.
    converter = time.gmtime

    def __init__(self, fmt=None, datefmt=None):
        if fmt is None:
            fmt = self.FORMAT
        if datefmt is None:
            datefmt = self.DATEFMT
        super(StructuredFormatter, self).__init__(fmt, datefmt)

    def format(self, record):
        """Format message, with escaped quotes and structured tags."""
        record.message = self.escape_quotes(record.getMessage())

        # this is verbatim from the parent class in stdlib
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__

        # add our structured tags *before* exception info is added
        structured = getattr(record, '_structured', {})
        if structured:
            logfmt = (self.logfmt(k, record.__dict__[k]) for k in structured)
            s += " " + " ".join(logfmt)

        # this is verbatim from the parent class in stdlib
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
            except UnicodeError:  # pragma: no cover
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
        return s.replace('"', '\\"')

    def remove_quotes(self, s):
        return s.replace('"', '')

    def logfmt(self, k, v):
        # we need unicode strings so as to be able to replace
        if isinstance(k, bytes):
            k = k.decode('utf8')
        if not isinstance(v, str):
            if isinstance(v, bytes):
                v = v.decode('utf8')
            elif not isinstance(v, str):
                v = str(v)

        k = k.replace(' ', '_').replace('"', '')
        k = self.remove_quotes(k)
        v = self.remove_quotes(v)
        if ' ' in v:
            v = '"' + v + '"'
        return "%s=%s" % (k, v)
