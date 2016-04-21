#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

install_requires = [
    'gunicorn==19.4.5',
    'Werkzeug==0.11.5',
    'statsd==3.2.1',
    'requests==2.9.1',
    'future==0.15.2',
]

test_requires = [
    'flake8>=2.4.1',
    'pytest>=2.9.1',
    'freezegun>=0.3.6',
    'mock>=2.0.0',
    'coverage>=4.0',
]

setup(
    name='talisker',
    version='0.1.0',
    description="A common WSGI stack",
    long_description=readme + '\n\n' + history,
    author="Simon Davy",
    author_email='simon.davy@canonical.com',
    url='https://github.com/bloodearnest/talisker',
    packages=['talisker'],
    package_dir={'talisker': 'talisker'},
    include_package_data=True,
    license="GPL3",
    zip_safe=False,
    keywords='talisker',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    install_requires=install_requires,
    test_suite='tests',
    tests_require=test_requires,
    setup_requires=['pytest-runner'],
    entry_points={
        'console_scripts': ['talisker=talisker.gunicorn:run'],
    }
)
