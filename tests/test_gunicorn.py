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
import datetime
import logging
import os
import subprocess
import sys

from gunicorn.config import Config

from talisker import gunicorn
from talisker import logs
from talisker import statsd


def test_talisker_entrypoint():
    entrypoint = 'talisker.gunicorn'
    subprocess.check_output([entrypoint, '--help'])


def test_gunicorn_logger_set_formatter_on_access_log():
    cfg = Config()
    cfg.set('accesslog', '/tmp/log')
    logger = gunicorn.GunicornLogger(cfg)
    access = logger._get_gunicorn_handler(logger.access_log)
    assert isinstance(access.formatter, logs.StructuredFormatter)


def test_gunicorn_logger_no_handler_for_stderr_access_log():
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    assert logger.access_log.propagate is True
    assert logger._get_gunicorn_handler(logger.access_log) is None


def test_gunicorn_logger_propagate_error_log():
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)
    assert logger.error_log.propagate is True
    assert len(logger.error_log.handlers) == 0


class TestResponse:
    status_code = 200
    status = '200 OK'
    sent = 1000
    headers = []


def access_extra_args(environ, url='/'):
    response = TestResponse()
    response.headers.append(('X-View-Name', 'view'))
    delta = datetime.timedelta(seconds=1)
    parts = url.split('?')
    path = parts[0]
    qs = parts[1] if len(parts) > 1 else ''
    environ['RAW_URI'] = url
    environ['HTTP_X_FORWARDED_FOR'] = '203.0.113.195, 150.172.238.178'
    environ['QUERY_STRING'] = qs
    environ['PATH_INFO'] = path
    environ['REMOTE_ADDR'] = '127.0.0.1'
    environ['HTTP_REFERER'] = 'referrer'
    environ['HTTP_USER_AGENT'] = 'ua'
    expected = OrderedDict()
    expected['method'] = 'GET'
    expected['path'] = path
    expected['qs'] = qs
    expected['status'] = 200
    expected['view'] = 'view'
    expected['duration'] = 1000.0
    expected['ip'] = '127.0.0.1'
    expected['proto'] = 'HTTP/1.0'
    expected['length'] = 1000
    expected['referrer'] = 'referrer'
    expected['forwarded'] = '203.0.113.195, 150.172.238.178'
    expected['ua'] = 'ua'
    return response, environ, delta, expected


def test_gunicorn_get_response_status():
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)

    class Response1:
        status_code = 200
    assert logger.get_response_status(Response1()) == 200

    class Response2:
        status = '200 OK'
    assert logger.get_response_status(Response2()) == 200

    class Response3:
        status = 200
    assert logger.get_response_status(Response3()) == 200


def test_gunicorn_logger_get_extra(environ):
    response, environ, delta, expected = access_extra_args(
        environ, '/foo?bar=baz')
    cfg = Config()
    logger = gunicorn.GunicornLogger(cfg)
    msg, extra = logger.get_extra(response, None, environ, delta, 200)
    assert msg == 'GET /foo?'
    assert extra == expected


def test_gunicorn_logger_access(environ, log, statsd_metrics):
    response, environ, delta, expected = access_extra_args(
        environ, '/')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected
    assert log[0].msg == 'GET /'

    assert 'gunicorn.views.view.GET.200:' in statsd_metrics[0]


def test_gunicorn_logger_access_no_view(environ, log, statsd_metrics):
    response, environ, delta, expected = access_extra_args(
        environ, '/')
    response.headers = []
    expected.pop('view')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected
    assert log[0].msg == 'GET /'

    assert 'gunicorn.requests.GET.200:' in statsd_metrics[0]


def test_gunicorn_logger_access_no_forwarded(environ, log, statsd_metrics):
    response, environ, delta, expected = access_extra_args(
        environ, '/')
    environ.pop('HTTP_X_FORWARDED_FOR')
    response.headers = [('X-View-Name', 'view')]
    expected.pop('forwarded')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected
    assert log[0].msg == 'GET /'

    assert 'gunicorn.views.view.GET.200:' in statsd_metrics[0]


def test_gunicorn_logger_access_forwarded(environ, log, statsd_metrics):
    response, environ, delta, expected = access_extra_args(
        environ, '/')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected
    assert log[0].msg == 'GET /'

    assert 'gunicorn.views.view.GET.200:' in statsd_metrics[0]


def test_gunicorn_logger_access_qs(environ, log):
    response, environ, delta, expected = access_extra_args(
        environ, '/url?foo=bar')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)

    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected
    assert log[0].msg == 'GET /url?'


def test_gunicorn_logger_access_with_request_id(environ, log):
    rid = 'request-id'
    response, environ, delta, expected = access_extra_args(
        environ, '/')
    response.headers.append(('X-Request-Id', rid))
    expected['request_id'] = rid
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)

    log[:] = []
    logger.access(response, None, environ, delta)
    assert log[0]._structured == expected


def test_gunicorn_logger_status_url(environ, log, statsd_metrics):
    response, environ, delta, expected = access_extra_args(
        environ, '/_status/ping')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    statsd.get_client()  # force the statsd creationg log message
    log[:] = []
    logger.access(response, None, environ, delta)
    assert len(log) == 0
    assert len(statsd_metrics) == 0


def test_gunicorn_logger_status_url_enabled(
        environ, log, statsd_metrics, monkeypatch):
    response, environ, delta, expected = access_extra_args(
        environ, '/_status/ping')
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    statsd.get_client()  # force the statsd creationg log message
    log[:] = []
    monkeypatch.setitem(os.environ, 'TALISKER_LOGSTATUS', 'true')
    logger.access(response, None, environ, delta)
    assert len(log) == 1
    assert len(statsd_metrics) == 0


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.logger_class == gunicorn.GunicornLogger
    assert app.cfg.loglevel.lower() == 'info'
    assert logs.get_talisker_handler().level == logging.NOTSET


def test_gunicorn_application_init_devel(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.accesslog == '-'
    assert app.cfg.timeout == 99999
    assert app.cfg.reload


def test_gunicorn_application_init_devel_overriden(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--timeout', '10'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.timeout == 10


def test_gunicorn_application_config_errorlog(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--log-file', '/tmp/log'])
    app = gunicorn.TaliskerApplication('')
    record = log[0]
    assert 'ignoring gunicorn errorlog' in record.msg
    assert record._structured['errorlog'] == '/tmp/log'
    assert app.cfg.errorlog == '-'


def test_gunicorn_application_config_loglevel_debug_devel(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--log-level', 'debug'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.loglevel.lower() == 'debug'
    assert logs.get_talisker_handler().level == logging.DEBUG


def test_gunicorn_application_config_statsd(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--statsd-host', 'localhost:8125'])
    app = gunicorn.TaliskerApplication('')
    record = log[0]
    assert 'ignoring gunicorn statsd' in record.msg
    assert record._structured['statsd_host'] == ('localhost', 8125)
    assert app.cfg.statsd_host is None
    assert app.cfg.statsd_prefix is None


def test_gunicorn_application_config_logger_class(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--logger-class', 'gunicorn.glogging.Logger'])
    from gunicorn.glogging import Logger
    app = gunicorn.TaliskerApplication('')
    record = log[0]
    assert 'using custom gunicorn logger class' in record.msg
    assert record._structured['logger_class'] is Logger
    assert app.cfg.logger_class is Logger


def wsgi(environ, start_response):
    start_response('200 OK', [])
    return ''


def test_gunicorn_application_load(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv', ['', __name__ + ':wsgi', '--bind=0.0.0.0:0'])
    app = gunicorn.TaliskerApplication('')
    wsgiapp = app.load_wsgiapp()
    assert wsgiapp._talisker_wrapped
    assert wsgiapp._talisker_original_app == wsgi
