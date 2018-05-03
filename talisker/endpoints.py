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

from builtins import *  # noqa

import collections
from datetime import datetime
import functools
import html
import logging
from ipaddress import ip_address, ip_network
from itertools import chain
import os
import sys
from werkzeug.wrappers import Request, Response
import talisker.revision
from talisker.util import module_cache, pkg_is_installed


__all__ = ['private']


class TestException(Exception):
    pass


def force_unicode(s):
    if isinstance(s, bytes):
        return s.decode('utf8')
    return s


@module_cache
def get_networks():
    network_tokens = os.environ.get('TALISKER_NETWORKS', '').split()
    networks = [ip_network(force_unicode(n)) for n in network_tokens]
    if networks:
        logger = logging.getLogger(__name__)
        logger.info('configured TALISKER_NETWORKS',
                    extra={'networks': ','.join(str(n) for n in networks)})
    return networks


PRIVATE_BODY_RESPONSE_TEMPLATE = """
IP address {0} not in trusted network.

REMOTE_ADDR: {1}
X-Forwarded-For: {2}
""".lstrip('\n')


def private(f):
    """Only allow approved source addresses."""

    @functools.wraps(f)
    def wrapper(self, request):
        if not request.access_route:
            # this means something probably bugged in werkzeug, but let's fail
            # gracefully
            return Response('no client ip provided', status='403')
        ip_str = request.access_route[-1]
        if isinstance(ip_str, bytes):
            ip_str = ip_str.decode('utf8')
        ip = ip_address(ip_str)
        if ip.is_loopback or any(ip in network for network in get_networks()):
            return f(self, request)
        else:
            msg = PRIVATE_BODY_RESPONSE_TEMPLATE.format(
                ip_str,
                force_unicode(request.remote_addr),
                request.headers.get('x-forwarded-for'))
            return Response(msg, status='403')
    return wrapper


@module_cache
def ok_response():
    return Response(str(talisker.revision.get()) + '\n')


class StandardEndpointMiddleware(object):
    """WSGI middleware to provide a standard set of endpoints for a service"""

    urlmap = collections.OrderedDict((
        ('', 'index'),
        ('/index', 'index'),
        ('/check', 'check'),
        ('/metrics', None),
        ('/ping', 'ping'),
        ('/info/packages', 'packages'),
        ('/info/workers', None),
        ('/info/logtree', None),
        ('/info/objgraph', None),
        ('/test/sentry', 'error'),
        ('/test/statsd', 'test_statsd'),
        ('/test/prometheus', None),
    ))

    no_index = {'', '/', '/index', '/error'}

    def __init__(self, app, namespace='_status'):
        self.app = app
        self.namespace = namespace
        self.prefix = '/' + namespace
        # Publish /metrics only if prometheus_client is available
        if pkg_is_installed('prometheus-client'):
            self.urlmap['/metrics'] = 'metrics'
            self.urlmap['/test/prometheus'] = 'test_prometheus'
        if pkg_is_installed('logging-tree'):
            self.urlmap['/info/logtree'] = 'logtree'
        if pkg_is_installed('psutil'):
            self.urlmap['/info/workers'] = 'workers'
        if pkg_is_installed('objgraph'):
            self.urlmap['/info/objgraph'] = 'objgraph'

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.path.startswith(self.prefix):
            path = request.path[len(self.prefix):].rstrip('/')
            try:
                funcname = self.urlmap[path]
                func = getattr(self, funcname)
            except (KeyError, AttributeError):
                # didn't find /_status endpoint, so pass thru to the app
                return self.app(environ, start_response)
            else:
                response = func(request)

            return response(environ, start_response)
        else:
            return self.app(environ, start_response)

    def index(self, request):
        methods = []
        for url, funcname in self.urlmap.items():
            if funcname is None:
                continue
            if url in self.no_index:
                continue
            try:
                func = getattr(self, funcname)
                methods.append(
                    link(url, self.prefix + url) + ' - ' + str(func.__doc__),
                )
            except AttributeError:
                pass
        return html_response(ul(methods))

    def ping(self, request):
        """HAProxy status check"""
        return ok_response()

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
                response = b''.join(response)

        if 'exc' in start:
            return Response('error', status=500)
        elif start.get('status', '').startswith('404'):
            # app does not provide /_status/nagios endpoint
            return ok_response()
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
    def test_statsd(self, request):
        """Increment statsd metric for testing"""
        statsd = request.environ['statsd']
        statsd.incr('test')
        return Response('Incremented {}.test'.format(statsd._prefix))

    @private
    def test_prometheus(self, request):
        """Increment prometheus metric for testing"""
        if not pkg_is_installed('prometheus-client'):
            return Response('Not Supported', status=501)

        if not hasattr(self, 'test_counter'):
            import prometheus_client
            self.test_counter = prometheus_client.Counter('test', 'test')
        self.test_counter.inc()
        return Response('Incremented test counter')

    @private
    def metrics(self, request):
        """Endpoint exposing Prometheus metrics"""
        if not pkg_is_installed('prometheus-client'):
            return Response('Not Supported', status=501)

        # Importing this too early would break multiprocess metrics
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            CollectorRegistry,
            REGISTRY,
            generate_latest,
            multiprocess,
        )

        if 'prometheus_multiproc_dir' in os.environ:
            # prometheus_client is running in multiprocess mode.
            # Use a custom registry, as the global one includes custom
            # collectors which are not supported in this mode
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
        else:
            if request.environ.get('wsgi.multiprocess', False):
                return Response(
                    'Not Supported: running in multiprocess mode but '
                    '`prometheus_multiproc_dir` envvar not set',
                    status=501)

            # prometheus_client is running in single process mode.
            # Use the global registry (includes CPU and RAM collectors)
            registry = REGISTRY

        data = generate_latest(registry)
        return Response(data, status=200, mimetype=CONTENT_TYPE_LATEST)

    @private
    def logtree(self, request):
        """Display the stdlib logging configuration."""
        import logging_tree
        tree = logging_tree.format.build_description()
        return Response(tree)

    @private
    def packages(self, request):
        """List of python packages installed."""
        import pip
        pkgs = pip.get_installed_distributions()
        pkgs.sort(key=lambda p: p.project_name)
        rows = []
        for p in pkgs:
            rows.append((
                p.project_name,
                p._version,
                link(
                    'PyPI',
                    'https://pypi.org/project/{}/{}/',
                    html.escape(p.project_name),
                    html.escape(p._version),
                ),
            ))

        return html_response(table(rows))

    @private
    def workers(self, request):
        """Information about workers resource usage."""
        import psutil
        arbiter = psutil.Process(os.getppid())
        workers = arbiter.children()
        workers.sort(key=lambda p: p.pid)

        rows = [format_psutil_row('Gunicorn Master', arbiter)]
        for i, worker in enumerate(workers):
            rows.append(format_psutil_row('Worker {}'.format(i), worker))

        return html_response(table(rows, headers=HEADERS))

    @private
    def objgraph(self, request):
        import objgraph
        types = objgraph.most_common_types(shortnames=False)
        leaking = objgraph.most_common_types(
            objects=objgraph.get_leaking_objects(), shortnames=False)
        return html_response(
            ['<h2>Most Common Objects</h2>'],
            table(types),
            ['<h2>Leaking Objects</h2>'],
            table(leaking),
        )


# diy html templating
cdn = '//cdnjs.cloudflare.com/ajax/libs'
css = [
    """
    <link rel="stylesheet"
    href="{cdn}/twitter-bootstrap/4.1.1/css/bootstrap.min.css">
    <link rel="stylesheet"
    href="{cdn}/bootstrap-table/1.12.1/bootstrap-table.min.css">
    <script
    src="{cdn}/jquery/3.3.1/jquery.js"></script>
    <script
    src="{cdn}/twitter-bootstrap/4.1.1/js/bootstrap.min.js"></script>
    <script
    src="{cdn}/bootstrap-table/1.12.1/bootstrap-table.min.js"></script>
    """.format(cdn=cdn)
]


def html_response(*iters):
    body = chain(css, *iters)
    return Response(body, mimetype='text/html')


def table(data, headers=None):
    css_class = "table table-striped table-hover table-bordered"
    yield '<table class="{}">'.format(css_class)
    if headers is not None:
        yield '<thead><tr>'
        for header in headers:
            yield '<th>{}</th>'.format(header)
        yield '</tr></thead>'
    yield '<tbody>'
    for row in data:
        yield '<tr>'
        for col in row:
            yield '<td>{}</td>'.format(col)
        yield '</tr>'
    yield '</tbody>'
    yield '</table>'


def ul(items):
    yield '<ul>'
    for item in items:
        yield '<li>{}</li>'.format(item)
    yield '</ul>'


def link(text, href, *args, **kwargs):
    return '<a href="{}">{}</a>'.format(
        href.format(*args, **kwargs),
        html.escape(text.format(*args, **kwargs)),
    )


MASTER_FIELDS = [
    'cwd',
    'cmdline',
    'exe',
    # permissions
    'uids',
    'gids',
    'terminal',

]

PSUTIL_FIELDS = [
    'pid',
    'create_time',
    'username',
    'nice',
    'memory_percent',
    'memory_full_info',
    'num_fds',
    'open_files',
    'cpu_percent',
    'num_threads',
]

HEADERS = [
    'Name',
    'PID',
    'User',
    'Nice',
    'VSS',
    'RSS',
    'USS',
    'Shared',
    'CPU%',
    'Mem%',
    'Uptime',
    'TCP Conns',
    'Open Files',
    'FDs',
    'Threads',
]


def mb(x):
    return '{}MB'.format(x // 1000000)


def format_psutil_row(name, process):
    data = process.as_dict(PSUTIL_FIELDS)
    uptime = datetime.now() - datetime.fromtimestamp(data['create_time'])
    # = datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    return [
        name,
        data['pid'],
        data['username'],
        data['nice'],
        mb(data['memory_full_info'].vms),
        mb(data['memory_full_info'].rss),
        mb(data['memory_full_info'].uss),
        mb(data['memory_full_info'].shared),
        '{:.1f}%'.format(data['cpu_percent']),
        '{:.1f}%'.format(data['memory_percent']),
        '{:.0f}m'.format(uptime.total_seconds() // 60),
        len(process.connections(kind='tcp')),
        len(data['open_files']),
        data['num_fds'],
        data['num_threads'],
    ]
