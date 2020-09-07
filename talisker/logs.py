#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

from collections import OrderedDict
from contextlib import contextmanager
import logging
import logging.handlers
import numbers
import sys
import time

from talisker.context import Context, ContextId
from talisker.util import (
    get_errno_fields,
    module_cache,
    module_dict,
)


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


class LoggingContextProxy():

    def __getattr__(self, attr):
        return getattr(Context.logging, attr)

    @contextmanager
    def __call__(self, extra=None, **kwargs):
        with Context.logging(extra, **kwargs):
            yield


logging_context = LoggingContextProxy()


# backwards compat aliases
def set_logging_context(*args, **kwargs):
    Context.logging.push(*args, **kwargs)


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
    if config.colour:
        formatter = ColouredFormatter(style=config.colour)

    # always INFO to stderr
    add_talisker_handler(logging.INFO, get_talisker_handler(), formatter)

    configure_warnings(config.devel)
    supress_noisy_logs()

    # defer this until logging has been set up
    logger = logging.getLogger(__name__)
    config_extra = {k: v.value for k, v in config.metadata().items() if v.raw}
    if config_extra:
        logger.info('talisker configured', extra=config_extra)
    if config.ERRORS:
        errors = {name: str(err) for name, err in config.ERRORS.items()}
        logger.error('configuration errors', extra=errors)

    if config.debuglog is not None:
        if can_write_to_file(config.debuglog):
            handler = logging.handlers.TimedRotatingFileHandler(
                config.debuglog,
                when='D',
                interval=1,
                backupCount=1,
                delay=True,
                utc=True,
            )
            handler._debug_handler = True
            add_talisker_handler(logging.DEBUG, handler)
            logger.info('enabling debug log', extra={'path': config.debuglog})
        else:
            logger.info('could not enable debug log, could not write to path',
                        extra={'path': config.debuglog})

    # sentry integration
    import talisker.sentry  # defer to avoid logging setup
    if talisker.sentry.enabled:
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


def configure_test_logging(handler=None):
    """Add a handler (defaults to NullHandler) to root logger.

    Prevents unconfigured logging from erroring, and swallows all logging,
    which is usually what you want for unit tests.  Unit test fixtures can
    still add their own loggers to assert against log messages if needed.
    """
    set_logger_class()
    if handler is None:
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
        # - context : local_context.flat
        # - global  : logging_globals['extra']
        #
        # In case of collisions, we append _ to the end of the name, so no data
        # is lost. The global ones are more important, so take priority - the
        # user supplied keys are the ones renamed if needed
        # Also, the ordering is specific - more specific tags first
        trailer = None
        structured = OrderedDict()

        try:
            if ContextId.get(None) is None:
                context_extra = {}
                request_id = None
            else:
                context_extra = logging_context.flat
                request_id = Context.request_id

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
            if request_id:
                structured['request_id'] = request_id
        except Exception:
            # ensure unexpected error doesn't break logging completely
            structured = extra

        kwargs = dict(func=func, extra=structured, sinfo=sinfo)
        # python 2 doesn't support sinfo parameter
        if sys.version_info[0] == 2:
            kwargs.pop('sinfo')
        record = super(StructuredLogger, self).makeRecord(
            name, level, fn, lno, msg, args, exc_info, **kwargs)
        # store extra explicitly for StructuredFormatter to use
        record.extra = structured
        record._structured = structured  # b/w compat
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
        import talisker.sentry  # lazy to break import cycle
        try:
            record.message = self.clean_message(record.getMessage())

            # we never want sentry to capture DEBUG logs in its breadcrumbs, as
            # they may be sensitive
            if record.levelno > logging.DEBUG:
                talisker.sentry.record_log_breadcrumb(record)

            if len(record.message) > self.MAX_MSG_SIZE:
                record.message = (
                    record.message[:self.MAX_MSG_SIZE] + self.TRUNCATED
                )

            # this is verbatim from the parent class in stdlib
            if self.usesTime():
                record.asctime = self.formatTime(record, self.datefmt)
            s = self._fmt % record.__dict__

            # add our structured tags *before* exception info is added
            structured = getattr(record, 'extra', {})
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
                # Cache the traceback text to avoid converting it multiple
                # times (it's constant anyway)
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
                    s = s + record.exc_text.decode(
                        sys.getfilesystemencoding(), 'replace')
            return s
        except Exception:
            # ensure unexpected error doesn't break logging
            return super().format(record)

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


DEFAULT_COLOURS = {
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


COLOUR_SCHEMES = {}
COLOUR_SCHEMES['default'] = DEFAULT_COLOURS

# simple strips italics/bold
COLOUR_SCHEMES['simple'] = DEFAULT_COLOURS.copy()
COLOUR_SCHEMES['simple']['logfmt'] = '0;36'
COLOUR_SCHEMES['simple']['msg'] = '0;37'
COLOUR_SCHEMES['simple']['time'] = '0;34'


class ColouredFormatter(StructuredFormatter):
    """Colourised log formatting"""
    CLEAR = '\x1b[0m'

    def __init__(self, style='default'):
        style = COLOUR_SCHEMES[style]
        self.colours = {k: '\x1b[' + v + 'm' for k, v in style.items()}
        format = (
            '{time}%(asctime)s.%(msecs)03dZ{clear} '
            '%(coloured_levelname)s '
            '{name}%(name)s{clear} '
            '"{msg}%(message)s{clear}"'
        ).format(clear=self.CLEAR, **self.colours)
        super().__init__(fmt=format)

    def format(self, record):
        colour = self.colours[record.levelname]
        record.coloured_levelname = '{colour}{levelname}{clear}'.format(
            colour=colour,
            levelname=record.levelname,
            clear=self.CLEAR,
        )
        return super(ColouredFormatter, self).format(record)

    def logfmt(self, structured):
        logfmt_str = super(ColouredFormatter, self).logfmt(structured)
        return self.colours['logfmt'] + logfmt_str + self.CLEAR
