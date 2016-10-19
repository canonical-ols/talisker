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

import sys
import subprocess
import os
from gunicorn.config import Config

from talisker import gunicorn
from talisker import logs


def test_talisker_entrypoint():
    entrypoint = os.environ['VENV_BIN'] + '/' + 'talisker'
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


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.logger_class == gunicorn.GunicornLogger
    assert app.cfg.loglevel == 'DEBUG'


def test_gunicorn_application_init_devel(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.accesslog == '-'
    assert app.cfg.timeout == 99999


def test_gunicorn_application_init_devel_overriden(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--timeout', '10'])
    app = gunicorn.TaliskerApplication('', devel=True)
    assert app.cfg.timeout == 10


def test_gunicorn_application_warn_errorlog(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--log-file', '/tmp/log'])
    gunicorn.TaliskerApplication('')
    record = log[0]
    assert 'ignoring gunicorn errorlog' in record.msg
    assert record._structured['errorlog'] == '/tmp/log'


def test_gunicorn_application_warn_statsd(monkeypatch, log):
    monkeypatch.setattr(
        sys, 'argv',
        ['talisker', 'wsgi:app', '--statsd-host', 'localhost:8125'])
    gunicorn.TaliskerApplication('')
    record = log[0]
    assert 'ignoring gunicorn statsd' in record.msg
    assert record._structured['statsd_host'] == 'localhost:8125'


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
