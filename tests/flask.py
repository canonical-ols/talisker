from flask import Flask
import talisker.flask

app = Flask(__name__)

talisker.flask.register(app)


@app.route('/')
def index():
    return 'ok'


@app.route('/error')
def error():
    raise Exception('test')
