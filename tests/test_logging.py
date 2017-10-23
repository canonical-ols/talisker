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

import raven.context

from talisker import logs


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
    except Exception:
        assert 0, "failed to parse logfmt: " + log
    return date + " " + time, level, name, msg, extra


def test_logging_context_ctx():
    with logs.logging_context(a=1):
        assert logs.logging_context.flat == {'a': 1}
        with logs.logging_context(a=2):
            assert logs.logging_context.flat == {'a': 2}
        assert logs.logging_context.flat == {'a': 1}


def test_logging_context_push():
    logs.logging_context.push(a=1)
    assert logs.logging_context.flat == {'a': 1}
    logs.logging_context.push(a=2)
    assert logs.logging_context.flat == {'a': 2}
    logs.logging_context.pop()
    assert logs.logging_context.flat == {'a': 1}
    logs.logging_context.pop()
    assert logs.logging_context.flat == {}


# b/w compat test
def test_set_logging_context():
    logs.set_logging_context(a=1)
    assert logs.logging_context.flat == {'a': 1}


# b/w compat test
def test_extra_logging():
    with logs.extra_logging({'a': 1}):
        assert logs.logging_context.flat == {'a': 1}


def test_make_record_no_extra():
    logger = logs.StructuredLogger('test')
    record = logger.makeRecord(*record_args())
    assert record._structured == {}


def test_make_record_global_extra():
    logger = logs.StructuredLogger('test')
    logs.set_global_extra({'a': 1})
    record = logger.makeRecord(*record_args())
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_context_extra():
    logger = logs.StructuredLogger('test')
    logs.logging_context.push(a=1)
    record = logger.makeRecord(*record_args())
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_all_extra():
    logger = logs.StructuredLogger('test')
    logs.set_global_extra({'a': 1})
    logs.logging_context.push(b=2)
    record = logger.makeRecord(*record_args(), extra={'c': 3})

    assert record.__dict__['a'] == 1
    assert record.__dict__['b'] == 2
    assert record.__dict__['c'] == 3
    assert record._structured == {'a': 1, 'b': 2, 'c': 3}


def test_make_record_extra_renamed():
    logger = logs.StructuredLogger('test')
    logs.set_global_extra({'a': 1})
    record = logger.makeRecord(*record_args(), extra={'a': 2})
    assert record._structured == {'a': 1, 'a_': 2}


def test_make_record_context_renamed():
    logger = logs.StructuredLogger('test')
    logs.set_global_extra({'a': 1})
    logs.logging_context.push(a=2)
    record = logger.makeRecord(*record_args())
    assert record._structured == {'a': 1, 'a_': 2}


def test_make_record_ordering():
    logger = logs.StructuredLogger('test')
    logs.set_global_extra({'global': 1})
    logs.logging_context.push(context=2)
    extra = OrderedDict()
    extra['user1'] = 3
    extra['user2'] = 4
    record = logger.makeRecord(*record_args(), extra=extra)
    assert list(record._structured.keys()) == [
        'user1', 'user2', 'context', 'global']


def test_logger_collects_raven_breadcrumbs():
    logger = logs.StructuredLogger('test')
    with raven.context.Context() as ctx:
        logger.info('info', extra={'foo': 'bar'})
        logger.debug('debug', extra={'foo': 'bar'})
        breadcrumbs = ctx.breadcrumbs.get_buffer()

    assert len(breadcrumbs) == 1
    assert breadcrumbs[0]['message'] == 'info'
    assert breadcrumbs[0]['level'] == 'info'
    assert breadcrumbs[0]['category'] == 'test'
    assert breadcrumbs[0]['data'] == {'extra': {'foo': 'bar'}}


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


def test_formatter_escapes_newlines():
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({'a': 'b'}, msg='some \nmessage'))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    # check quotes doesn't break parsing
    assert msg == 'some \\nmessage'
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
    except Exception:
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


def test_formatter_large_msg(monkeypatch):
    monkeypatch.setattr(logs.StructuredFormatter, 'MAX_MSG_SIZE', 5)
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({}, msg='1234567890'))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    assert msg == "12345...<truncated>"
    assert structured == {}


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


def assert_output_includes_message(err, msg):
    lines = err.split('\n')
    assert all(parse_logfmt(l) for l in lines if l)
    assert msg in err


def test_configure(config, capsys):
    logs.configure(config)
    assert not isinstance(
        logs.get_talisker_handler().formatter, logs.ColoredFormatter)
    logger = logging.getLogger('test')
    logger.info('test msg')
    out, err = capsys.readouterr()
    assert out == ""
    assert err, "No stderr output"
    assert_output_includes_message(err, 'INFO test "test msg"')


def test_configure_twice(config):
    logs.configure(config)
    logs.configure(config)
    handlers = logging.getLogger().handlers
    talisker_handlers = [h for h in handlers
                         if hasattr(h, '_talisker_handler')]
    assert len(talisker_handlers) == 2  # root and sentry


def assert_record_logged(log, msg, logger, level, extra={}):
    for record in log:
        if (record.levelname == level and
           record.name == logger and
           msg in record.msg and
           record._structured == extra):
                break
    else:
        assert 0, "Could not find record in log"


def test_configure_debug_log_bad_file(config, log):
    config['debuglog'] = '/nopenopenope'
    logs.configure(config)
    assert_record_logged(
        log,
        msg='could not',
        logger='talisker.logs',
        level='INFO',
        extra={'path': '/nopenopenope'})


def test_configure_debug_log(config, log):
    tmp = tempfile.mkdtemp()
    logfile = os.path.join(tmp, 'log')
    config['debuglog'] = logfile
    logs.configure(config)
    assert_record_logged(
        log,
        msg='enabling',
        logger='talisker.logs',
        level='INFO',
        extra={'path': logfile})


def test_configure_colored(config, log, monkeypatch):
    config['color'] = True
    logs.configure(config)
    assert isinstance(
        logs.get_talisker_handler().formatter, logs.ColoredFormatter)


def test_clean_message():
    fmt = logs.StructuredFormatter()
    assert fmt.clean_message('foo') == 'foo'
    assert fmt.clean_message('foo "bar"') == r'foo \"bar\"'
    assert fmt.clean_message('foo "bar"') == r'foo \"bar\"'
    assert fmt.clean_message('foo\nbar') == r'foo\nbar'


def test_logfmt_no_value():
    structured = {'a': 1, 'b': None, 'c': ''}
    logfmt = logs.StructuredFormatter().logfmt(structured)
    parsed = shlex.split(logfmt)
    assert parsed == ['a=1']


def test_logfmt_atom(monkeypatch):
    fmt = logs.StructuredFormatter()
    assert fmt.logfmt_atom('foo', 'bar') == 'foo="bar"'
    # quoting
    assert fmt.logfmt_atom('foo', 'string') == 'foo="string"'
    assert fmt.logfmt_atom('foo', 1) == 'foo=1'
    assert fmt.logfmt_atom('foo', True) == 'foo=true'
    input = {'foo': 'bar"withquote'}
    # str(dict) is different in python 2/3, due to u'' prefix of keys
    expected = str({'foo': 'barwithquote'})
    assert fmt.logfmt_atom('foo', input) == 'foo="' + expected + '"'
    # strip quotes
    assert fmt.logfmt_atom('foo', '"baz"') == r'foo="baz"'
    assert fmt.logfmt_atom('foo', 'bar "baz"') == r'foo="bar baz"'
    assert fmt.logfmt_atom('foo"', 'bar') == r'foo="bar"'
    # encoding
    assert fmt.logfmt_atom('foo', b'bar') == r'foo="bar"'
    assert fmt.logfmt_atom(b'foo', 'bar') == r'foo="bar"'
    # key replacement
    assert fmt.logfmt_atom('foo bar', 'baz') == r'foo_bar="baz"'
    assert fmt.logfmt_atom('foo=bar', 'baz') == r'foo_bar="baz"'
    assert fmt.logfmt_atom('foo.bar', 'baz') == r'foo_bar="baz"'
    # maxsize
    monkeypatch.setattr(logs.StructuredFormatter, 'MAX_VALUE_SIZE', 5)
    assert fmt.logfmt_atom('abcdefghij', 'foo') == r'abcde="foo"'
    assert fmt.logfmt_atom('foo', 'abcdefghij') == r'foo="abcde...<truncated>"'
