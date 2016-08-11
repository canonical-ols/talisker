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

import logging
import logging.handlers


import shlex
import time

from py.test import fixture

from .fixtures import clean_up_context  # noqa
from talisker import logs
from talisker.request_context import request_context

TIME = time.mktime((2016, 1, 17, 12, 30, 10, 1, 48, 0))
MSEC = 123.456
TIMESTAMP = "2016-01-17 12:30:10.123Z"


@fixture
def record_args():
    """Test arguments to the makeRecord function."""
    return ('name', logging.INFO, 'fn', 'lno', 'msg here', tuple(), None)


def make_record(extra):
    """Make a test record from StructuredLogger."""
    logger = logs.StructuredLogger('test')
    record = logger.makeRecord(*record_args(), extra=extra)
    # stub out the time
    record.__dict__['created'] = TIME
    record.msecs = MSEC
    return record


def parse_logfmt(log):
    """Stupid simple logfmt parser"""
    parsed = shlex.split(log)
    date, time, level, name, msg = parsed[:5]
    extra = dict((v.split('=')) for v in parsed[5:])
    return date + " " + time, level, name, msg, extra


def test_set_logging_context_no_extra():
    if hasattr(request_context, 'extra'):
        del request_context.extra
    logs.set_logging_context()
    assert request_context.extra == {}


def test_set_logging_context():
    logs.set_logging_context(a=1)
    assert request_context.extra == {'a': 1}


def test_make_record_no_extra(record_args):
    logger = logs.StructuredLogger('test')
    record = logger.makeRecord(*record_args)
    assert record._structured == {}


def test_make_record_global_extra(record_args):
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    record = logger.makeRecord(*record_args)
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_context_extra(record_args):
    logger = logs.StructuredLogger('test')
    logs.set_logging_context(a=1)
    record = logger.makeRecord(*record_args)
    assert record.__dict__['a'] == 1
    assert record._structured == {'a': 1}


def test_make_record_all_extra(record_args):
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    logs.set_logging_context(b=2)
    record = logger.makeRecord(*record_args, extra={'c': 3})

    assert record.__dict__['a'] == 1
    assert record.__dict__['b'] == 2
    assert record.__dict__['c'] == 3
    assert record._structured == {'a': 1, 'b': 2, 'c': 3}


def test_make_record_context_overiddes(record_args):
    logger = logs.StructuredLogger('test')
    logger.update_extra({'a': 1})
    logs.set_logging_context(a=2)
    record = logger.makeRecord(*record_args)

    assert record.__dict__['a'] == 2
    assert record._structured == {'a': 2}


def test_formatter_no_args():
    fmt = logs.StructuredFormatter()
    log = fmt.format(make_record({}))
    timestamp, level, name, msg, structured = parse_logfmt(log)
    assert timestamp == TIMESTAMP
    assert level == 'INFO'
    assert name == 'name'
    assert msg == "msg here"
    assert structured == {}


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


def test_formatter_with_exec_info():
    fmt = logs.StructuredFormatter()
    record = make_record({'foo': 'bar'})
    record.exc_info = True
    record.exc_text = "Traceback:\none\ntwo\nthree"
    log = fmt.format(record)
    lines = log.splitlines()
    timestamp, level, name, msg, structured = parse_logfmt(lines[0])
    assert structured['foo'] == 'bar'
    assert lines[1] == 'Traceback:'
    assert lines[2] == 'one'
    assert lines[3] == 'two'
    assert lines[4] == 'three'


def test_configure(capsys):
    logs.configure(logging.INFO, tags=dict(foo='bar baz'))
    logger = logging.getLogger('test')
    logger.info('test msg')
    out, err = capsys.readouterr()
    assert out == ""
    assert err
    timestamp, level, name, msg, structured = parse_logfmt(err)
    assert level == 'INFO'
    assert name == 'test'
    assert msg == 'test msg'
    assert structured['foo'] == 'bar baz'


def test_escape_quotes():
    fmt = logs.StructuredFormatter()
    assert fmt.escape_quotes('foo') == 'foo'
    assert fmt.escape_quotes('foo "bar"') == r'foo \"bar\"'


def test_logfmt():
    fmt = logs.StructuredFormatter()
    assert fmt.logfmt('foo', 'bar') == 'foo=bar'
    assert fmt.logfmt('foo', 'bar baz') == 'foo="bar baz"'
    assert fmt.logfmt('foo', '"baz"') == r'foo=baz'
    assert fmt.logfmt('foo', 'bar "baz"') == r'foo="bar baz"'
    assert fmt.logfmt('foo', b'bar') == r'foo=bar'
    assert fmt.logfmt(b'foo', 'bar') == r'foo=bar'
    assert fmt.logfmt('foo foo', 'bar') == r'foo_foo=bar'
    assert fmt.logfmt('foo"', 'bar') == r'foo=bar'
    assert fmt.logfmt('foo"', 1) == r'foo=1'
