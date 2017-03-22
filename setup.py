#!/usr/bin/env python
#
# Note: this file is autogenerated from setup.cfg for older setuptools
#
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

attrs = {
    "classifiers": [
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware",
        "Topic :: System :: Logging",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5"
    ],
    "author": "Simon Davy",
    "description": "A common WSGI stack",
    "name": "talisker",
    "url": "https://github.com/canonical-ols/talisker",
    "license": "GPL3",
    "author_email": "simon.davy@canonical.com",
    "version": "0.9.0",
    "keywords": [
        "talisker"
    ],
    "entry_points": {
        "console_scripts": [
            "talisker=talisker.gunicorn:run",
            "talisker.run=talisker:run",
            "talisker.gunicorn=talisker.gunicorn:run",
            "talisker.celery=talisker.celery:main"
        ]
    },
    "extras_require": {
        "prometheus": [
            "prometheus-client>=0.0.17,<0.1"
        ],
        "flask": [
            "flask>=0.11,<0.13",
            "blinker>=1.4,<2.0"
        ],
        "django": [
            "django>=1.8,<1.11"
        ],
        "celery": [
            "celery>=3.1.13.0,<5.0"
        ],
        "dev": [
            "logging_tree",
            "pygments"
        ]
    },
    "package_dir": {
        "talisker": "talisker"
    },
    "include_package_data": True,
    "packages": [
        "talisker"
    ],
    "zip_safe": False,
    "install_requires": [
        "gunicorn>=19.5.0,<20.0",
        "Werkzeug>=0.11.5,<0.13",
        "statsd>=3.2.1,<4.0",
        "requests>=2.10.0,<3.0",
        "raven>=5.27.0,<7.0",
        "future>=0.15.2,<0.17",
        "ipaddress>=1.0.16,<2.0;python_version<\"3.3\""
    ],
    "package_data": {
        "talisker": [
            "logstash/*"
        ]
    },
    "test_suite": "tests"
}

attrs['long_description'] = open('README.rst').read()
setup(**attrs)
