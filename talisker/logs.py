from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from collections import OrderedDict
import logging
import sys

from .request_context import request_context


_logging_configured = False


def set_logging_context(extra=None, **kwargs):
    """Update structured logging keys in a thread/context dict."""
    if not hasattr(request_context, 'extra'):
        request_context.extra = {}
    if extra:
        request_context.extra.update(extra)
    if kwargs:
        request_context.extra.update(kwargs)


def configure(level=logging.INFO, devel=False, tags=None):
    """Configure default logging setup for our services.

    This is basically:
     - log to stderr
     - output hybrid logfmt structured format
     - add some basic structured data by default

    Additionally, we set the 'requests' logger to WARNING.
    """

    # avoid duplicate logging
    global _logging_configured
    if _logging_configured:
        return

    if tags is not None:
        StructuredLogger.update_extra(tags)

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

    warnings = logging.getLogger('py.warnings')
    warnings.propagate = False

    if devel:
        enable_devel_logging()

    _logging_configured = True


def enable_devel_logging():
    # we only want warnings in development, and not structured
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

    _extra = OrderedDict()
    _prefix = 'svc.'
    structured = True

    @classmethod
    def update_extra(cls, extra):
        cls._extra.update(extra)

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        # at this point we have 3 possible sources of extra kwargs
        # - global  : cls._extra
        # - context : local.extra
        # - log call: extra
        all_extra = self._extra.copy()
        all_extra.update(getattr(request_context, 'extra', {}))
        if extra is not None:
            # prefix call site extra args, to avoid collisions
            for k, v in list(extra.items()):
                all_extra[self._prefix + k] = v
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
        # this is verbatim from the parent class in stdlib
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__

        # add our structured tags *before* exeception info is added
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
        return s.replace('"', '\\"')

    def logfmt(self, k, v):
        # we need unicode strings so as to be able to replace
        if isinstance(k, bytes):
            k = k.decode('utf8')
        if isinstance(v, bytes):
            v = v.decode('utf8')
        v = self.escape_quotes(v)
        if ' ' in v:
            v = '"' + v + '"'
        return "%s=%s" % (k, v)
