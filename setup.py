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

requirements = open('requirements.txt').readlines()

test_requirements = open('requirements_dev.txt').readlines()

setup(
    name='talisker',
    version='0.1.0',
    description="A common WSGI stack",
    long_description=readme + '\n\n' + history,
    author="Simon Davy",
    author_email='simon.davy@canonical.com',
    url='https://github.com/bloodearnest/talisker',
    packages=[
        'talisker',
    ],
    package_dir={'talisker':
                 'talisker'},
    include_package_data=True,
    install_requires=requirements,
    license="GPL3",
    zip_safe=False,
    keywords='talisker',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
