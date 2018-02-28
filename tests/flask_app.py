from flask import Flask
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, MetaData, select


import talisker.flask
from talisker.postgresql import TaliskerConnection

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
conn.execute(select([users]))


app = Flask(__name__)
talisker.flask.register(app)

talisker.requests.get_session().post(
    'http://httpbin.org/post', json={'foo': 'bar'})


@app.route('/')
def index():
    talisker.requests.get_session().post(
        'http://httpbin.org/post', json={'foo': 'bar'})
    return 'ok'


@app.route('/error/')
def error():
    conn.execute(select([users]))
    talisker.requests.get_session().post(
        'http://httpbin.org/post', json={'foo': 'bar'})
    raise Exception('test')
