from datetime import timedelta
import requests
import talisker.requests


# @pytest.fixture
def response(
        method='GET',
        host='http://example.com',
        url='/',
        code=200,
        elapsed=1.0):
    req = requests.Request(method, host + url)
    resp = requests.Response()
    resp.request = req.prepare()
    resp.status_code = code
    resp.elapsed = timedelta(seconds=elapsed)
    return resp


def test_metric_hook_root():
    r = response()
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com._.GET.200'
    assert duration == 1000.0


def test_metric_hook_no_trailing_slash():
    r = response(url='')
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com._.GET.200'
    assert duration == 1000.0


def test_metric_hook_url():
    r = response(url='/foo/bar')
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com._foo_bar.GET.200'
    assert duration == 1000.0


def test_metric_hook_post_and_500():
    r = response(method='POST', code=500)
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com._.POST.500'
    assert duration == 1000.0

