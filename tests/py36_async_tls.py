# test for monkeypatched async https in py36
# https://github.com/requests/requests/issues/3752
import requests
import flask

app = flask.Flask(__name__)


@app.route('/')
def home():
    r = requests.get("https://httpbin.org/get")
    r.raise_for_status()
    return 'OK'
