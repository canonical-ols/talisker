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

from talisker import statsd


def test_parse_statsd_dsn_host():
    parsed = statsd.parse_statsd_dsn('udp://test.com')
    assert parsed == ('test.com', 8125, None, 512, False)


def test_parse_statsd_dsn_port():
    parsed = statsd.parse_statsd_dsn('udp://test.com:5000')
    assert parsed == ('test.com', 5000, None, 512, False)


def test_parse_statsd_dsn_prefix():
    parsed = statsd.parse_statsd_dsn('udp://test.com/foo.bar')
    assert parsed == ('test.com', 8125, 'foo.bar', 512, False)


def test_parse_statsd_dsn_prefix_with_slashes():
    parsed = statsd.parse_statsd_dsn('udp://test.com/foo/bar')
    assert parsed == ('test.com', 8125, 'foo.bar', 512, False)


def test_parse_statsd_dsn_size():
    parsed = statsd.parse_statsd_dsn('udp://test.com?maxudpsize=1024')
    assert parsed == ('test.com', 8125, None, 1024, False)


def test_parse_statsd_dsn_ipv6():
    parsed = statsd.parse_statsd_dsn('udp6://test.com')
    assert parsed == ('test.com', 8125, None, 512, True)


def test_client_properties():
    client = statsd.TaliskerStatsdClient()
    assert client.hostname == '127.0.0.1'
    assert client.port == 8125
    assert client.hostport == '127.0.0.1:8125'
    assert client.ipv6 is False
    assert client.prefix is None
    assert client.maxudpsize == 512
