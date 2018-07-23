##
## Copyright (c) 2015-2018 Canonical, Ltd.
##
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
##
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##
import collections
from setuptools.config import read_configuration

config = read_configuration('setup.cfg')
data = {}
collections.OrderedDict()
data.update(config['metadata'])
data.update(config['options'])
data['long_description'] = 'DESCRIPTION'

long_description = open('README.rst').read().strip()
sorted_data = collections.OrderedDict((k, data[k]) for k in sorted(data))


def print_line(k, v, indent='    '):
    if isinstance(v, list):
        print('{}{}=['.format(indent, k))
        for i in v:
            print("{}    '{}',".format(indent, i))
        print('{}],'.format(indent))
    elif isinstance(v, dict):
        print('{}{}=dict('.format(indent, k))
        for k2 in sorted(v):
            print_line(k2, v[k2], indent + '    ')
        print('{}),'.format(indent))
    elif isinstance(v, bool):
        print("{}{}={},".format(indent, k, v))
    elif k == 'long_description':
        print("{}{}={},".format(indent, k, v))
    else:
        print("{}{}='{}',".format(indent, k, v))


print("""#!/usr/bin/env python
##
## Copyright (c) 2015-2018 Canonical, Ltd.
##
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
##
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

#
# Note: this file is autogenerated from setup.cfg for older setuptools
#
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

DESCRIPTION = '''
{}
'''

setup(""".format(long_description))

for k, v in sorted_data.items():
    print_line(k, v)

print(')')
