##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

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
import pytest

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
    fmt = logs.StructuredFormatter()
    with raven.context.Context() as ctx:
        fmt.format(make_record({'foo': 'bar'}, 'info'))
        record = make_record({'foo': 'bar'}, 'info')
        record.levelno = logging.DEBUG
        record.levelname = 'debug'
        fmt.format(record)
        breadcrumbs = ctx.breadcrumbs.get_buffer()

    assert len(breadcrumbs) == 1
    assert breadcrumbs[0]['message'] == 'info'
    assert breadcrumbs[0]['level'] == 'info'
    assert breadcrumbs[0]['category'] == 'name'
    assert breadcrumbs[0]['data'] == {
        'foo': 'bar',
        'lineno': 'lno',
        'path': 'fn',
    }


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
        e = Exception()
        e.errno = 101
        e.strerror = 'some error'
        raise e
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
    assert structured == {
        'errno': 'ENETUNREACH',
        'strerror': 'some error',
    }
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
    assert msg == "12345..."
    assert structured == {}


def test_colored_formatter():
    fmt = logs.ColoredFormatter()
    record = make_record({})
    output = fmt.format(record)
    assert logs.DEFAULT_COLORS['time'] in output
    assert logs.DEFAULT_COLORS['INFO'] in record.colored_levelname
    logfmt = fmt.logfmt({'foo': 'bar'})
    assert logs.DEFAULT_COLORS['logfmt'] in logfmt


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
    assert len(talisker_handlers) == 3  # root and sentry and test logger


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
    config['color'] = 'default'
    logs.configure(config)
    assert isinstance(
        logs.get_talisker_handler().formatter, logs.ColoredFormatter)


def test_clean_message():
    fmt = logs.StructuredFormatter()
    assert fmt.clean_message('foo') == 'foo'
    assert fmt.clean_message('foo "bar"') == r'foo \"bar\"'
    assert fmt.clean_message('foo "bar"') == r'foo \"bar\"'
    assert fmt.clean_message('foo\nbar') == r'foo\nbar'


@pytest.mark.parametrize('input,expected', [
    ('hi', 'hi'),
    (b'hi', 'hi'),
    ('hi hi', 'hi_hi'),
    ('hi.hi', 'hi_hi'),
    ('hi=hi', 'hi_hi'),
    ('hi"hi', 'hi\\"hi'),
    (1, '1'),
    ((1,), None),
    (True, None),
    (False, None),
    ('hi\nhi\nhi', 'hi___'),
])
def test_logfmt_key(input, expected):
    fmt = logs.StructuredFormatter()
    assert fmt.logfmt_key(input) == expected


def test_logfmt_key_truncate():
    fmt = logs.StructuredFormatter()
    fmt.MAX_KEY_SIZE = 5
    assert fmt.logfmt_key('1234567890') == '12345___'
    # check newlines and max length
    assert fmt.logfmt_key('123\n456\n789\n0') == '123___'


@pytest.mark.parametrize('input,expected', [
    ('hi', 'hi'),
    ('10', '"10"'),
    (b'hi', 'hi'),
    (' hi "hi" ', '"hi \\\"hi\\\""'),
    (True, 'true'),
    (False, 'false'),
    (1, '1'),
    ({}, '"' + str(type({})) + '"'),
    ([1, 2, 3], '"' + str(type([])) + '"'),
    ('hi\nhi\nhi', 'hi...'),
])
def test_logfmt_value(input, expected):
    fmt = logs.StructuredFormatter()
    assert fmt.logfmt_value(input) == expected


def test_logfmt_value_truncate():
    fmt = logs.StructuredFormatter()
    fmt.MAX_VALUE_SIZE = 5
    assert fmt.logfmt_value('1234567890') == '12345...'
    # check newlines and max length
    assert fmt.logfmt_value('123\n456\n789\n0') == '123...'


@pytest.mark.parametrize('input,expected', [
    ({'foo': 'bar'}, [('foo', 'bar')]),
    ({'foo': 1}, [('foo', '1')]),
    ({'foo': '1'}, [('foo', '"1"')]),
    ({'foo': True}, [('foo', 'true')]),
    ({'foo': False}, [('foo', 'false')]),
    ({'foo': None}, []),
    ({'foo': ''}, []),
    ({(1,): 'baz'}, []),
])
def test_logfmt_atoms(input, expected):
    fmt = logs.StructuredFormatter()
    assert list(fmt.logfmt_atoms(input)) == expected


def test_logfmt_atoms_subdict(monkeypatch, log):
    fmt = logs.StructuredFormatter()

    # dicts
    subdict = OrderedDict()
    subdict['int'] = 1
    subdict['intstr'] = "1"
    subdict['bool'] = True
    subdict['string'] = 'string'
    subdict['long'] = '12345678901234567890'
    subdict['dict'] = {'key': 'value'}
    subdict['list'] = [1, 2, 3]
    subdict[2] = 'int key'
    subdict[(3,)] = 'bad key'

    expected = [
        ('foo_int', '1'),
        ('foo_intstr', '"1"'),
        ('foo_bool', 'true'),
        ('foo_string', 'string'),
        ('foo_long', '1234567890...'),
        ('foo_dict', '"' + str(type({})) + '"'),
        ('foo_list', '"' + str(type([])) + '"'),
        ('foo_2', '"int key"'),
    ]

    monkeypatch.setattr(fmt, 'MAX_VALUE_SIZE', 10)
    input = {
        'foo': subdict,
        (4,): 'bad_key',
    }
    assert list(fmt.logfmt_atoms(input)) == expected
    assert 'could not parse logfmt' in log[-1].msg
    assert '(3,)' in log[-1].msg
    assert '(4,)' in log[-1].msg


@pytest.mark.parametrize('input, expected', [
    ('string', False),
    ('space space', True),
    ('foo=bar', True),
    ('\"hi\"', True),
    ('\\tescaped', True),
    ('1234567890', True),
    ('1234567890a', False),
    ('12.34', True),
    ('12.34.56', False),
])
def test_string_needs_quoting(input, expected):
    fmt = logs.StructuredFormatter()
    assert fmt.string_needs_quoting(input) == expected


@pytest.mark.parametrize('input, expected', [
    ('test', 'test'),
    ('newline\nnewline', 'newline...'),
    ('longlonglong', 'longlon...'),
    ('"quote"', '\\"quote\\"'),
])
def test_safe_string(input, expected):
    fmt = logs.StructuredFormatter()
    assert fmt.safe_string(input, 7, '...') == expected
