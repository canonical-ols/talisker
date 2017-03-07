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
import logging.handlers
import sys
import time

from talisker.context import ContextStack
from talisker.util import module_dict, module_cache


__all__ = [
    'configure',
    'configure_logging',
    'configure_test_logging',
    'logging_context',
]


logging_globals = module_dict()


def set_global_extra(extra):
    if 'extra' not in logging_globals:
        logging_globals['extra'] = OrderedDict()
    logging_globals['extra'].update(extra)


def reset_logging():
    """Reset logging config"""
    logging.getLogger().handlers = []


NOISY_LOGS = {
    'requests': logging.WARNING,
}


logging_context = ContextStack('logging')

# backwards compat alias
set_logging_context = logging_context.push
extra_logging = logging_context


def add_talisker_handler(level, handler, formatter=None):
    if formatter is None:
        formatter = StructuredFormatter()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    handler._talisker_handler = True
    logging.getLogger().addHandler(handler)


def set_logger_class():
    logging.setLoggerClass(StructuredLogger)
    logging.getLogger().setLevel(logging.NOTSET)


@module_cache
def get_talisker_handler():
    handler = logging.StreamHandler()
    handler._root_talisker = True
    return handler


def configure(config):  # pragma: no cover
    """Configure default logging setup for our services.

    This is basically:
     - log to stderr
     - output hybrid logfmt structured format
     - maybe configure debug logging
    """

    # avoid duplicate logging
    if logging_globals.get('configured'):
        return

    set_logger_class()
    formatter = StructuredFormatter()
    # note: we recheck isatty, incase devel mode has been forced with DEVEL=1
    if sys.stderr.isatty():
        formatter = ColoredFormatter()

    # always INFO to stderr
    add_talisker_handler(logging.INFO, get_talisker_handler(), formatter)

    configure_warnings(config['devel'])
    supress_noisy_logs()

    # defer this until logging has been set up
    logger = logging.getLogger(__name__)

    debug = config['debuglog']
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
            logger.info('enabling debug log', extra={'path': debug})
        else:
            logger.info('could not enable debug log, could not write to path',
                        extra={'path': debug})

    # sentry integration
    import talisker.sentry  # defer to avoid logging setup
    sentry_handler = talisker.sentry.get_log_handler()
    add_talisker_handler(logging.ERROR, sentry_handler)

    logging_globals['configured'] = True


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
    set_logger_class()
    handler = logging.NullHandler()
    add_talisker_handler(logging.NOTSET, handler)
    configure_warnings(True)


def enable_debug_log_stderr():
    """Enables debug logging on stderr

    Checks for devel mode."""
    logger = logging.getLogger(__name__)
    logger.warning('setting stderr logging to DEBUG')
    get_talisker_handler().setLevel(logging.DEBUG)


class StructuredLogger(logging.Logger):
    """A logger that handles passing 'extra' arguments to all logging calls.

    Supports 3 sources of extra structured data:

    1) global extra, designed to be set once at process start/
    2) context extra, designed to be set per request or job, can cleaned up
       afterwards.
    3) per call extra, passed by the log call, as per normal logging
       e.g. log.info('...', extra={...})

    """

    # sadly, we must subclass and override, rather that use the new
    # setLogRecordFactory() in 3.2+, as that does not pass the extra args
    # through. Also, we need to support python 2.
    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        # at this point we have 3 possible sources of extra kwargs
        # - log call: extra
        # - context : local.extra
        # - global  : cls._extra
        #
        # In case of collisions, we append _ to the end of the name, so no data
        # is lost. The global ones are more important, so take priority - the
        # user supplied keys are the ones renamed if needed
        # Also, the ordering is specific - more specific tags first
        structured = OrderedDict()
        context_extra = logging_context.flat
        global_extra = logging_globals.get('extra', {})

        if extra:
            for k, v in extra.items():
                if k in context_extra or k in global_extra:
                    k = k + '_'
                structured[k] = v

        for k, v in context_extra.items():
            if k in global_extra:
                k = k + '_'
            structured[k] = v

        structured.update(global_extra)

        kwargs = dict(func=func, extra=structured, sinfo=sinfo)
        # python 2 doesn't support sinfo parameter
        if sys.version_info[0] == 2:
            kwargs.pop('sinfo')
        record = super(StructuredLogger, self).makeRecord(
            name, level, fn, lno, msg, args, exc_info, **kwargs)
        # store extra explicitly for StructuredFormatter to use
        record._structured = structured
        return record

    def _log(self, level, msg, *args, **kwargs):
        # we never want sentry to capture DEBUG logs in its breadcrumbs, as
        # they may be sensitive
        import talisker.sentry
        if level > logging.DEBUG:
            talisker.sentry.record_log_breadcrumb(
                self, level, msg, *args, **kwargs)
        super()._log(level, msg, *args, **kwargs)


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
            s += " " + self.logfmt(structured)

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

    def logfmt(self, structured):
        logfmt = (self.logfmt_atom(*kv) for kv in structured.items())
        return " ".join(logfmt)

    def logfmt_atom(self, k, v):
        # we need unicode strings so as to be able to replace
        if isinstance(k, bytes):
            k = k.decode('utf8')
        if not isinstance(v, str):
            if isinstance(v, bytes):
                v = v.decode('utf8')
            elif not isinstance(v, str):
                # string representation
                v = str(v)

        k = k.strip()
        v = v.strip()
        # replace [ .=] with '_' in key
        # ' ' and = are replacd because they're are not valid logfmt (afaict)
        # . is replaced because elasticsearch can't do keys with . in
        k = k.replace(' ', '_').replace('.', '_').replace('=', '_')
        # strip " as grok parser can not escape them
        k = k.replace('"', '')
        v = v.replace('"', '')
        # quote if needed
        if any(c in v for c in ' =\t'):
            v = '"' + v + '"'
        return "%s=%s" % (k, v)


class ColoredFormatter(StructuredFormatter):
    """Colorized log formatting"""

    COLOR_LOGFMT = '\x1b[3;36m'
    COLOR_NAME = '\x1b[0;33m'
    COLOR_MSG = '\x1b[1;37m'
    COLOR_TIME = '\x1b[2;34m'
    CLEAR = '\x1b[0m'

    COLOR_LEVEL = {
        'DEBUG': '\x1b[0;32m',
        'INFO': '\x1b[0;32m',
        'WARNING': '\x1b[0;33m',
        'ERROR': '\x1b[0;31m',
        'CRITICAL': '\x1b[0;31m',
    }

    FORMAT = (
        COLOR_TIME + '%(asctime)s.%(msecs)03dZ ' + CLEAR +
        '%(colored_levelname)s ' +
        COLOR_NAME + '%(name)s ' + CLEAR +
        '"' + COLOR_MSG + '%(message)s' + CLEAR + '"'
    )

    def format(self, record):
        record.colored_levelname = (
            self.COLOR_LEVEL[record.levelname] +
            record.levelname + self.CLEAR)
        return super(ColoredFormatter, self).format(record)

    def logfmt(self, structured):
        logfmt_str = super(ColoredFormatter, self).logfmt(structured)
        return self.COLOR_LOGFMT + logfmt_str + self.CLEAR
