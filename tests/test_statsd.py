import pytest
import os

from talisker import statsd


def test_get_client_from_env():
    client = statsd.get_client_from_env()
    assert client._addr == ('127.0.0.1', 8125)
    assert client._prefix is None


def test_get_client_from_env_dsn(monkeypatch):
    monkeypatch.setitem(os.environ, 'STATSD_DSN', 'prefix@1.2.3.4:9000')
    client = statsd.get_client_from_env()
    assert client._addr == ('1.2.3.4', 9000)
    assert client._prefix == 'prefix'


def test_get_client_from_env_env(monkeypatch):
    monkeypatch.setitem(os.environ, 'STATSD_HOST', '1.2.3.4')
    monkeypatch.setitem(os.environ, 'STATSD_PORT', '9000')
    monkeypatch.setitem(os.environ, 'STATSD_PREFIX', 'prefix')
    client = statsd.get_client_from_env()
    assert client._addr == ('1.2.3.4', 9000)
    assert client._prefix == 'prefix'
