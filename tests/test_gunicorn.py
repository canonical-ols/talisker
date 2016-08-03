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
from gunicorn.config import Config

from talisker import gunicorn
from talisker import logs
from talisker import statsd

from freezegun import freeze_time


@freeze_time('2016-01-02 03:04:05.6789')
def test_gunicorn_logger_now():
    logger = gunicorn.GunicornLogger(Config())
    ts = logger.now()
    assert ts == '[02/Jan/2016:03:04:05.678 +0000]'


def test_gunicorn_logger_set_formatters_on_gunicorn_logs():
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    error = logger._get_gunicorn_handler(logger.error_log)
    assert isinstance(error.formatter, logs.StructuredFormatter)
    access = logger._get_gunicorn_handler(logger.access_log)
    assert isinstance(access.formatter, logs.StructuredFormatter)


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.access_log_format == gunicorn.access_log_format
    assert app.cfg.logger_class == gunicorn.GunicornLogger


def test_gunicorn_application_init_statsd(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['talisker', 'wsgi:app'])
    statsd_config = {'hostport': '1.2.3.4:2000', 'prefix': 'test'}
    monkeypatch.setattr(statsd, 'get_config', lambda: statsd_config)
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.statsd_host == ('1.2.3.4', 2000)
    assert app.cfg.statsd_prefix == 'test'


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


def test_parse_environ():
    parse = gunicorn.parse_environ
    assert parse({}) == (False, None)
    assert parse({'DEVEL': 1}) == (True, None)
    assert parse({'DEBUGLOG': '/tmp/log'}) == (False, '/tmp/log')
    assert parse({'DEVEL': 1, 'DEBUGLOG': '/tmp/log'}) == (True, '/tmp/log')
