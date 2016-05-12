from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import os
import functools
from ipaddress import ip_address, ip_network
from werkzeug.wrappers import Request, Response
from talisker import revision


class TestException(Exception):
    pass


NETWORKS = []
_loaded = False


def load_networks():
    networks = os.environ.get('TALISKER_NETWORKS', '').split(' ')
    return [ip_network(n) for n in networks if n]


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
        ip = ip_address(request.access_route[0])
        if ip.is_loopback or any(ip in network for network in NETWORKS):
            return f(self, request)
        else:
            return Response(status='403')
    return wrapper


class StandardEndpointMiddleware(object):
    """WSGI middleware to provide a standard set of endpoints for a service"""

    _ok = Response('OK. Revision: ' + str(revision.get()))

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
                response = getattr(self, method)(request)
            except AttributeError:
                response = Response(status=404)

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

        response = self.app(request.environ, nagios_start)
        if start['status'].startswith('404'):
            # app does not provide /_status/nagios endpoint
            return self._ok
        else:
            # return app's response
            return Response(response,
                            status=start['status'],
                            headers=start['headers'])

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
