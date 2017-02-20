#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

install_requires = [
    'gunicorn>=19.5.0,<20.0',
    'Werkzeug>=0.11.5,<0.12',
    'statsd>=3.2.1,<4.0',
    'requests>=2.10.0,<3.0',
    'raven>=5.3.1,<6.0',
    'future>=0.15.2,<0.16',
]

if sys.version_info < (3, 3):
    install_requires.append('ipaddress>=1.0.16,<2.0')

setup(
    name='talisker',
    version='0.9.0',
    description="A common WSGI stack",
    long_description=readme + '\n\n' + history,
    author="Simon Davy",
    author_email='simon.davy@canonical.com',
    url='https://github.com/canonical-ols/talisker',
    packages=['talisker'],
    package_dir={'talisker': 'talisker'},
    package_data={'talisker': ['logstash/*']},
    include_package_data=True,
    license="GPL3",
    zip_safe=False,
    keywords='talisker',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
        'Topic :: System :: Logging',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    install_requires=install_requires,
    extras_require={
        'celery': ["celery>=3.1.0"],
        'prometheus': ["prometheus-client==0.0.17"],
        'flask': ["flask>=0.11,<0.12", "blinker>=1.4,<2.0"],
    },
    test_suite='tests',
    entry_points={
        'console_scripts': [
            # TODO: make naked talisker talisker.run? b/w compat break...
            'talisker=talisker.gunicorn:run',
            'talisker.run=talisker:run',
            'talisker.gunicorn=talisker.gunicorn:run',
            'talisker.celery=talisker.celery:main',
        ],
    }
)
