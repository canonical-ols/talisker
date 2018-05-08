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
import numbers
import sys
import time

from talisker.context import ContextStack
from talisker.util import module_dict, module_cache, get_errno_fields


__all__ = [
    'configure',
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
    # avoid unclosed file resource warning
    for handler in logging.getLogger().handlers:
        if getattr(handler, '_debug_handler', False):
            handler.stream.close()
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
    if config['color']:
        formatter = ColoredFormatter(style=config['color'])

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
            handler._debug_handler = True
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
    except Exception:
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
    handler = logging.FileHandler('/dev/null')
    add_talisker_handler(logging.NOTSET, handler)
    configure_warnings(True)


def enable_debug_log_stderr():
    """Enables debug logging on stderr

    Checks for devel mode."""
    logger = logging.getLogger(__name__)
    logger.warning('setting stderr logging to DEBUG')
    get_talisker_handler().setLevel(logging.DEBUG)


# our enhanced version of the default raven support for recording breadcrumbs
def record_log_breadcrumb(record):
    # lazy import avoids any raven loggers being initialised early
    from raven import breadcrumbs

    breadcrumb_handler_args = (
        logging.getLogger(record.name),
        record.levelno,
        record.message,
        record.args,
        {
            'extra': record._structured,
            'exc_info': record.exc_info,
            'stack_info': getattr(record, 'stack_info', None)
        },
    )

    for handler in getattr(breadcrumbs, 'special_logging_handlers', []):
        if handler(*breadcrumb_handler_args):
            return

    handler = breadcrumbs.special_logger_handlers.get(record.name)
    if handler is not None and handler(*breadcrumb_handler_args):
        return

    def processor(data):
        metadata = {
            'path': record.pathname,
            'lineno': record.lineno,
        }
        if hasattr(record, 'func'):
            metadata['func'] = record.func
        metadata.update(record._structured)
        data.update({
            'message': record.message,
            'category': record.name,
            'level': record.levelname.lower(),
            'data': metadata,
        })
    breadcrumbs.record(processor=processor)


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
        # - context : local_context.flat
        # - global  : logging_globals['extra']
        #
        # In case of collisions, we append _ to the end of the name, so no data
        # is lost. The global ones are more important, so take priority - the
        # user supplied keys are the ones renamed if needed
        # Also, the ordering is specific - more specific tags first
        trailer = None
        structured = OrderedDict()
        context_extra = logging_context.flat
        global_extra = logging_globals.get('extra', {})

        if extra:
            trailer = extra.pop('trailer', None)
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
        record._trailer = trailer
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
    MAX_MSG_SIZE = 1024 * 10
    MAX_KEY_SIZE = 256
    MAX_VALUE_SIZE = 1024
    TRUNCATED = '...'
    TRUNCATED_KEY = '___'  # keys cannot have . in

    # use utc time. No idea why this is not the default.
    converter = time.gmtime

    def __init__(self, fmt=None, datefmt=None):
        if fmt is None:
            fmt = self.FORMAT
        if datefmt is None:
            datefmt = self.DATEFMT
        super(StructuredFormatter, self).__init__(fmt, datefmt)

    def format(self, record):
        """Format message with structured tags and any exception/trailer"""
        record.message = self.clean_message(record.getMessage())

        # we never want sentry to capture DEBUG logs in its breadcrumbs, as
        # they may be sensitive
        if record.levelno > logging.DEBUG:
            record_log_breadcrumb(record)

        if len(record.message) > self.MAX_MSG_SIZE:
            record.message = (
                record.message[:self.MAX_MSG_SIZE] + self.TRUNCATED
            )

        # this is verbatim from the parent class in stdlib
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__

        # add our structured tags *before* exception info is added
        structured = getattr(record, '_structured', {})
        if record.exc_info and 'errno' not in structured:
            structured.update(get_errno_fields(record.exc_info[1]))
        if structured:
            s += " " + self.logfmt(structured)
        # add talisker trailers
        trailer = getattr(record, '_trailer', None)
        if trailer is not None:
            s += '\n' + str(trailer)

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

    def clean_message(self, s):
        return s.replace('"', '\\"').replace('\n', '\\n')

    def logfmt(self, structured):
        formatted = (
            '{}={}'.format(k, v) for k, v in self.logfmt_atoms(structured))
        return " ".join(formatted)

    def logfmt_atoms(self, structured):
        """Generate logfmt atoms from a dict.

        In the case of a bad key, omit it.
        In the case of a bad value, emit key="???"
        """
        key_errors = []
        for k, v in structured.items():
            key = None
            try:
                if v is not False and not v:
                    continue

                key = self.logfmt_key(k)

                if key is None:
                    key_errors.append(k)
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        subkey = self.logfmt_key(k2)
                        if subkey is None:
                            key_errors.append(k2)
                        else:
                            yield (key + '_' + subkey, self.logfmt_value(v2))
                else:
                    yield key, self.logfmt_value(v)

            except Exception:
                if key is None:
                    key_errors.append(k)
                else:
                    yield key, '"???"'

        if key_errors:
            # we embed the keys in the message precisely because they
            # couldn't be parsed as logfmt key
            logger = logging.getLogger(__name__)
            logger.warning('could not parse logfmt keys: ' + str(key_errors))

    def logfmt_key(self, k):
        if isinstance(k, bytes):
            k = k.decode('utf8')

        if isinstance(k, str):
            k = k.replace(' ', '_').replace('.', '_').replace('=', '_')
            k = self.safe_string(k, self.MAX_KEY_SIZE, self.TRUNCATED_KEY)
            # TODO: look at measuring perf of this
            # ' ' and = are replaced because they're are not valid logfmt
            # . is replaced because elasticsearch can't do keys with . in
        elif isinstance(k, bool):
            # need to do this here, as bool are also numbers
            return None
        elif isinstance(k, numbers.Number):
            k = str(k)
        else:
            return None

        return k

    def logfmt_value(self, v):
        """Format a python value for logfmt.

        The output target here is influenced by logstash/elastic search types.

        For strings, ensures unicode, quotes, and truncates as needed.
        For bools, format as json truth values.
        For dicts, truncate.
        For others types (e.g. numbers) leave as is.
        For all else, coerce to string.
        """

        if isinstance(v, bytes):
            v = v.decode('utf8')
        if isinstance(v, str):
            v = self.safe_string(v, self.MAX_VALUE_SIZE, self.TRUNCATED)
            if self.string_needs_quoting(v):
                v = '"' + v + '"'
        elif isinstance(v, bool):
            v = str(v).lower()
        elif isinstance(v, numbers.Number):
            v = str(v)
        else:
            v = '"' + str(type(v)) + '"'

        return v

    def string_needs_quoting(self, v):
        all_numeric = True
        decimal_count = 0
        for c in v:
            if c in ' ="\\':
                return True
            if c not in '0123456789.':
                all_numeric = False
            elif c == '.':
                decimal_count += 1

        if all_numeric and decimal_count <= 1:
            return True

        return False

    def safe_string(self, s, max, truncate_str):
        truncated = False
        s = s.strip()

        # no new lines allowed, so truncate at the first new line
        if '\n' in s:
            s = s.split('\n', 1)[0]
            truncated = True

        # maximum size, to prevent overloading aggregator (accidental or
        # malicious)
        if len(s) > max:
            s = s[:max]
            truncated = True

        s = s.replace('"', '\\"')

        if truncated and truncate_str is not None:
            s = s + truncate_str

        return s


DEFAULT_COLORS = {
    'logfmt': '2;3;36',     # dim italic teal
    'name': '0;33',         # orange
    'msg': '1;16',          # bold white/black, depending on terminal palette
    'time': '2;34',         # dim dark blue
    'DEBUG': '0;32',        # green
    'INFO': '0;32',         # green
    'WARNING': '0;33',      # orange
    'ERROR': '0;31',        # red
    'CRITICAL': '0;31',     # red
}


COLOR_SCHEMES = {}
COLOR_SCHEMES['default'] = DEFAULT_COLORS

# simple strips italics/bold
COLOR_SCHEMES['simple'] = DEFAULT_COLORS.copy()
COLOR_SCHEMES['simple']['logfmt'] = '0;36'
COLOR_SCHEMES['simple']['msg'] = '0;37'
COLOR_SCHEMES['simple']['time'] = '0;34'


class ColoredFormatter(StructuredFormatter):
    """Colorized log formatting"""
    CLEAR = '\x1b[0m'

    def __init__(self, style='default'):
        style = COLOR_SCHEMES[style]
        self.colors = {k: '\x1b[' + v + 'm' for k, v in style.items()}
        format = (
            '{time}%(asctime)s.%(msecs)03dZ{clear} '
            '%(colored_levelname)s '
            '{name}%(name)s{clear} '
            '"{msg}%(message)s{clear}'
        ).format(clear=self.CLEAR, **self.colors)
        super().__init__(fmt=format)

    def format(self, record):
        color = self.colors[record.levelname]
        record.colored_levelname = '{color}{levelname}{clear}'.format(
            color=color,
            levelname=record.levelname,
            clear=self.CLEAR,
        )
        return super(ColoredFormatter, self).format(record)

    def logfmt(self, structured):
        logfmt_str = super(ColoredFormatter, self).logfmt(structured)
        return self.colors['logfmt'] + logfmt_str + self.CLEAR
