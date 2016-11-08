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

import sys
import logging
import logging.handlers
import os
import tempfile
from collections import OrderedDict

import shlex
import calendar

from talisker import logs
from talisker.request_context import request_context


TIME = calendar.timegm((2016, 1, 17, 12, 30, 10, 1, 48, 0))
MSEC = 123.456
TIMESTAMP = "2016-01-17 12:30:10.123Z"


def record_args(msg='msg here'):
    """Test arguments to the makeRecord function."""
    return ('name', logging.INFO, 'fn', 'lno', msg, tuple(), None)


def make_record(extra, msg='msg here'):
    """Make a test record from StructuredLogger."""
    logger = logs.StructuredLogger('test')
    record = logger.makeRecord(*record_args(msg), extra=extra)
    # stub out the time
    record.__dict__['created'] = TIME
    record.msecs = MSEC
    return record


def parse_logfmt(log):
    """Stupid simple logfmt parser"""
    parsed = shlex.split(log)
    date, time, level, name, msg = parsed[:5]
    try:
        extra = dict((v.split('=')) for v in parsed[5:])
    except:
        assert 0, "failed to parse logfmt: " + log
    return date + " " + time, level, name, msg, extra


def test_set_logging_context_no_extra():
    if hasattr(request_context, 'extra'):
        del request_context.extra
    logs.set_logging_context()
    assert request_context.extra == {}


def test_set_logging_context():
    logs.set_logging_context(a=1)
    assert request_context.extra == {'a': 1}


def test_set_logging_context_explicit_extra():
    logs.set_logging_context(extra={'a': 1})
    assert request_context.extra == {'a': 1}


def test_extra_logging():
    with logs.extra_logging({'a': 1}):
        assert request_context.extra == {'a': 1}


def test_make_record_no_extra():
    logger = logs.StructuredLogger('test')
    record = logger.makeRecord(*record_args())
    assert record._structured == {}


def test_make_record_global_extra():
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    record = logger.makeRecord(*record_args())
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_context_extra():
    logger = logs.StructuredLogger('test')
    logs.set_logging_context(a=1)
    record = logger.makeRecord(*record_args())
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_all_extra():
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    logs.set_logging_context(b=2)
    record = logger.makeRecord(*record_args(), extra={'c': 3})

    assert record.__dict__['a'] == 1
    assert record.__dict__['b'] == 2
    assert record.__dict__['c'] == 3
    assert record._structured == {'a': 1, 'b': 2, 'c': 3}


def test_make_record_extra_renamed():
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    record = logger.makeRecord(*record_args(), extra={'a': 2})
    assert record._structured == {'a': 1, 'a_': 2}


def test_make_record_context_renamed():
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    logs.set_logging_context(a=2)
    record = logger.makeRecord(*record_args())
    assert record._structured == {'a': 1, 'a_': 2}


def test_make_record_ordering():
    logger = logs.StructuredLogger('test')
    logger.update_extra({'global': 1})
    logs.set_logging_context(context=2)
    extra = OrderedDict()
    extra['user1'] = 3
    extra['user2'] = 4
    record = logger.makeRecord(*record_args(), extra=extra)
    assert list(record._structured.keys()) == [
            'user1', 'user2', 'context', 'global']


def test_formatter_no_args():
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({}))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    assert msg == "msg here"
    assert structured == {}


def test_formatter_escapes_quotes():
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({'a': 'b'}, msg='some " quotes'))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    # check quotes doesn't break parsing
    assert msg == 'some " quotes'
    assert structured == {'a': 'b'}


def test_formatter_with_extra():
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({'foo': 'bar', 'baz': 'with spaces'}))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    assert msg == "msg here"
    assert structured == {
        'foo': 'bar',
        'baz': 'with spaces',
    }


def test_formatter_with_exception():
    fmt = logs.StructuredFormatter()

    try:
        raise Exception()
    except:
        record = make_record({})
        record.exc_info = sys.exc_info()
        log = fmt.format(record)
    assert '\n' in log
    output = log.splitlines()
    timestamp, level, name, msg, structured = parse_logfmt(output[0])
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    assert msg == "msg here"
    assert structured == {}
    assert 'Traceback' in output[1]
    assert 'Exception' in output[-1]


def test_colored_formatter():
    CF = logs.ColoredFormatter
    assert CF.COLOR_TIME in CF.FORMAT
    assert CF.COLOR_NAME in CF.FORMAT
    assert CF.COLOR_MSG in CF.FORMAT
    fmt = CF()
    record = make_record({})
    fmt.format(record)
    assert CF.COLOR_LEVEL['INFO'] in record.colored_levelname
    logfmt = fmt.logfmt({'foo': 'bar'})
    assert CF.COLOR_LOGFMT in logfmt


def test_configure(capsys):
    logs.configure_logging()
    logger = logging.getLogger('test')
    logger.info('test msg')
    out, err = capsys.readouterr()
    assert out == ""
    assert err
    timestamp, level, name, msg, structured = parse_logfmt(err)
    assert level == 'INFO'
    assert name == 'test'
    assert msg == 'test msg'
    assert structured == {}


def test_configure_twice():
    logs.configure_logging()
    logs.configure_logging()
    handlers = logging.getLogger().handlers
    talisker_handlers = [h for h in handlers
                         if hasattr(h, '_talisker_handler')]
    assert len(talisker_handlers) == 1


def test_configure_debug_log_bad_file(capsys):
    logs.configure_logging(debug='/nopenopenope')
    out, err = capsys.readouterr()
    assert out == ""
    assert err
    timestamp, level, name, msg, structured = parse_logfmt(err)
    assert level == 'INFO'
    assert name == 'talisker.logs'
    assert 'could not' in msg
    assert structured['path'] == '/nopenopenope'


def test_configure_debug_log(capsys):
    tmp = tempfile.mkdtemp()
    logfile = os.path.join(tmp, 'log')
    logs.configure_logging(debug=logfile)
    out, err = capsys.readouterr()
    assert out == ""
    assert err
    timestamp, level, name, msg, structured = parse_logfmt(err)
    assert level == 'INFO'
    assert name == 'talisker.logs'
    assert 'enabling' in msg
    assert structured['path'] == logfile


def test_escape_quotes():
    fmt = logs.StructuredFormatter()
    assert fmt.escape_quotes('foo') == 'foo'
    assert fmt.escape_quotes('foo "bar"') == r'foo \"bar\"'


def test_logfmt_atom():
    fmt = logs.StructuredFormatter()
    assert fmt.logfmt_atom('foo', 'bar') == 'foo=bar'
    assert fmt.logfmt_atom('foo', 'bar baz') == 'foo="bar baz"'
    assert fmt.logfmt_atom('foo', '"baz"') == r'foo=baz'
    assert fmt.logfmt_atom('foo', 'bar "baz"') == r'foo="bar baz"'
    assert fmt.logfmt_atom('foo', b'bar') == r'foo=bar'
    assert fmt.logfmt_atom(b'foo', 'bar') == r'foo=bar'
    assert fmt.logfmt_atom('foo foo', 'bar') == r'foo_foo=bar'
    assert fmt.logfmt_atom('foo"', 'bar') == r'foo=bar'
    assert fmt.logfmt_atom('foo"', 1) == r'foo=1'
    assert fmt.logfmt_atom('foo', 'x=y') == r'foo="x=y"'


def test_parse_environ():
    parse = logs.parse_environ
    assert parse({}) == (False, None)
    assert parse({'DEVEL': 1}) == (True, None)
    assert parse({'DEBUGLOG': '/tmp/log'}) == (False, '/tmp/log')
    assert parse({'DEVEL': 1, 'DEBUGLOG': '/tmp/log'}) == (True, '/tmp/log')
