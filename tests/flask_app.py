import logging

from flask import Flask
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, MetaData, select
from werkzeug.wrappers import Response

import talisker.flask
from talisker.postgresql import TaliskerConnection

logger = logging.getLogger(__name__)
engine = sqlalchemy.create_engine(
    'postgresql://django_app:django_app@localhost:5432/django_app',
    connect_args={'connection_factory': TaliskerConnection},
)

metadata = MetaData()
users = Table(
    'users',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('fullname', String),
)

metadata.create_all(engine)
conn = engine.connect()
conn.execute(users.insert().values(name='jack', fullname='Jack Jones'))


app = Flask(__name__)
talisker.flask.register(app)


@app.route('/')
def index():
    return 'ok'


@app.route('/logging')
def logging():
    logger.info('info', extra={'foo': 'bar'})
    talisker.requests.get_session().post(
        'http://httpbin.org/post', json={'foo': 'bar'})
    return 'ok'


@app.route('/error/')
def error():
    conn.execute(select([users]))
    talisker.requests.get_session().post(
        'http://httpbin.org/post', json={'foo': 'bar'})
    raise Exception('test')


@app.route('/nested')
def nested():
    resp = talisker.requests.get_session().get('http://localhost:8001')
    return Response(resp.content, status=200, headers=resp.headers.items())
