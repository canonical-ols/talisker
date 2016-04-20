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
