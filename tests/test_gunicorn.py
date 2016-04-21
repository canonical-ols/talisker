import sys
from gunicorn.config import Config
from freezegun import freeze_time
from talisker import gunicorn
from talisker import logs
from talisker import statsd


@freeze_time('2016-01-02 03:04:05.6789')
def test_gunicorn_logger_now():
    logger = gunicorn.GunicornLogger(Config())
    ts = logger.now()
    assert ts == '[02/Jan/2016:03:04:05.678 +0000]'


def test_gunicorn_logger_setup_defaults():
    cfg = Config()
    cfg.set('accesslog', '-')
    logger = gunicorn.GunicornLogger(cfg)
    error = logger._get_gunicorn_handler(logger.error_log)
    assert isinstance(error.formatter, logs.StructuredFormatter)
    access = logger._get_gunicorn_handler(logger.access_log)
    assert isinstance(access.formatter, logs.StructuredFormatter)


def test_gunicorn_application_init(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['', ''])
    statsd_config = {'hostport': '1.2.3.4:2000', 'prefix': 'test'}
    monkeypatch.setattr(statsd, 'get_config', lambda: statsd_config)
    app = gunicorn.TaliskerApplication('')
    assert app.cfg.access_log_format == gunicorn.access_log_format
    assert app.cfg.logger_class == gunicorn.GunicornLogger


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
