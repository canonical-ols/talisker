# test for monkeypatched async https in py36
# https://github.com/requests/requests/issues/3752
import requests
import flask

app = flask.Flask(__name__)

print(requests.get("https://google.com"))
