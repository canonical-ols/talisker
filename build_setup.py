import collections
import json
from setuptools.config import read_configuration

config = read_configuration('setup.cfg')
data = collections.OrderedDict()
data.update(config['metadata'])
data.update(config['options'])
data.pop('long_description')

attrs = json.dumps(data, indent=4)

# hackhackhack
attrs = attrs.replace(': false', ': False')
attrs = attrs.replace(': true', ': True')


print("""
#!/usr/bin/env python
#
# Note: this file is autogenerated from setup.cfg for older setuptools
#
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

attrs = {}

attrs['long_description'] = open('README.rst').read()
setup(**attrs)
""".format(attrs).strip())
