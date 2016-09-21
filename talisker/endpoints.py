# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import os
import sys
import collections
import functools
from ipaddress import ip_address, ip_network
from werkzeug.wrappers import Request, Response
from talisker import revision


__all__ = []


class TestException(Exception):
    pass


NETWORKS = []
_loaded = False


def force_unicode(s):
    if isinstance(s, bytes):
        return s.decode('utf8')
    return s


def load_networks():
    networks = os.environ.get('TALISKER_NETWORKS', '').split(' ')
    return [ip_network(force_unicode(n)) for n in networks if n]


def private(f):
    """Only allow approved source addresses."""
    @functools.wraps(f)
    def wrapper(self, request):
        global NETWORKS, _loaded
        if not _loaded:
            NETWORKS = load_networks()
            _loaded = True
        if not request.access_route:
            # no client ip
            return Response(status='403')
        ip_str = request.access_route[0]
        if isinstance(ip_str, bytes):
            ip_str = ip_str.decode('utf8')
        ip = ip_address(ip_str)
        if ip.is_loopback or any(ip in network for network in NETWORKS):
            return f(self, request)
        else:
            return Response(status='403')
    return wrapper


class StandardEndpointMiddleware(object):
    """WSGI middleware to provide a standard set of endpoints for a service"""

    _ok_response = None

    @property
    def _ok(self):
        if self._ok_response is None:
            self._ok_response = Response(str(revision.get()))
        return self._ok_response

    def __init__(self, app, namespace='_status'):
        self.app = app
        self.namespace = namespace
        self.prefix = '/' + namespace

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.path.startswith(self.prefix):
            method = request.path[len(self.prefix):]
            if method == '':
                # no trailing /
                start_response('302', [('location', self.prefix + '/')])
                return ''
            if method == '/':
                method = 'index'
            else:
                method = method.lstrip('/')
            try:
                func = getattr(self, method)
            except AttributeError:
                response = Response(status=404)
            else:
                response = func(request)

            return response(environ, start_response)
        else:
            return self.app(environ, start_response)

    def index(self, request):
        methods = []
        item = '<li><a href="{0}"/>{0}</a> - {1}</li>'
        for name, func in list(self.__class__.__dict__.items()):
            if not name.startswith('_') and name != 'index':
                methods.append(item.format(name, func.__doc__))
        return Response(
            '<ul>' + '\n'.join(methods) + '<ul>', mimetype='text/html')

    def ping(self, request):
        """HAProxy status check"""
        return self._ok

    def check(self, request):
        """Nagios health check"""
        start = {}

        def nagios_start(status, headers, exc_info=None):
            # save status for inspection
            start['status'] = status
            start['headers'] = headers
            if exc_info:
                start['exc'] = sys.exc_info()

        response = self.app(request.environ, nagios_start)
        if not start:
            # nagios_start has not yet been called
            if isinstance(response, collections.Iterable):
                # force evaluation
                response = ''.join(response)

        if 'exc' in start:
            return Response('error', status=500)
        elif start.get('status', '').startswith('404'):
            # app does not provide /_status/nagios endpoint
            return self._ok
        else:
            # return app's response
            return Response(response,
                            status=start.get('status', 200),
                            headers=start.get('headers', []))

    @private
    def error(self, request):
        """Raise a TestError for testing"""
        raise TestException('this is a test, ignore')

    @private
    def metric(self, request):
        statsd = request.environ['statsd']
        statsd.incr('test')
        return Response('Incremented {}.test'.format(statsd._prefix))

    @private
    def info(self, request):
        return Response('Not Implemented', status=501)
