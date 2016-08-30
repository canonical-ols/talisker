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
    'gunicorn>=19.5.0',
    'Werkzeug>=0.11.5',
    'statsd>=3.2.1',
    'requests>=2.10.0',
    'future>=0.15.2',
]

if sys.version_info < (3, 3):
    install_requires.append('ipaddress==1.0.16')

setup(
    name='talisker',
    version='0.5.5',
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
    test_suite='tests',
    setup_requires=['pytest-runner'],
    entry_points={
        'console_scripts': ['talisker=talisker.gunicorn:run'],
    }
)
