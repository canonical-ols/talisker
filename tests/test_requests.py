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
    assert name == 'requests.example-com.GET.200'
    assert duration == 1000.0


def test_metric_hook_post():
    r = response(method='POST')
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.POST.200'
    assert duration == 1000.0


def test_metric_hook_500():
    r = response(code=500)
    name, duration = talisker.requests.get_timing(r)
    assert name == 'requests.example-com.GET.500'
    assert duration == 1000.0
