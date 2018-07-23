#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

import pytest
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


def test_dummyclient_basic(no_network):
    client = statsd.DummyClient()

    # check the basic methods don't error or use network
    client.incr('a')
    client.decr('a')
    client.timing('a', 1)
    client.gauge('a', 1)
    client.set('a', 1)
    timer = client.timer('a')
    timer.start()
    timer.stop()


def test_dummyclient_pipeline(no_network):
    client = statsd.DummyClient()
    with client.pipeline() as p:
        p.incr('a')
        p.decr('a')
        p.timing('a', 1)
        p.gauge('a', 1)
        p.set('a', 1)
        timer = p.timer('a')
        timer.start()
        timer.stop()

        assert p.stats[0] == 'a:1|c'
        assert p.stats[1] == 'a:-1|c'
        assert p.stats[2] == 'a:1.000000|ms'
        assert p.stats[3] == 'a:1|g'
        assert p.stats[4] == 'a:1|s'
        assert p.stats[5].startswith('a:')
        assert p.stats[5].endswith('|ms')


def test_dummyclient_nested_pipeline(no_network):
    client = statsd.DummyClient()
    with client.pipeline() as p1:
        with p1.pipeline() as p2:
            assert p1.stats is not p2.stats


def test_dummyclient_collect(no_network):
    client = statsd.DummyClient()
    with client.collect() as stats:
        client.incr('a')
        client.decr('a')
        client.timing('a', 1)
        client.gauge('a', 1)
        client.set('a', 1)
        timer = client.timer('a')
        timer.start()
        timer.stop()

        assert stats[0] == 'a:1|c'
        assert stats[1] == 'a:-1|c'
        assert stats[2] == 'a:1.000000|ms'
        assert stats[3] == 'a:1|g'
        assert stats[4] == 'a:1|s'
        assert stats[5].startswith('a:')
        assert stats[5].endswith('|ms')


@pytest.mark.xfail
def test_no_network(no_network):
    import socket
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def test_dummyclient_memory(no_network):
    client = statsd.DummyClient()
    assert client.stats is None
    for i in range(1000):
        client.incr('a')
    assert client.stats is None
