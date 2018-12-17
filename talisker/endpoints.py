#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import collections
from datetime import datetime
import functools
from ipaddress import ip_address
import logging
import os
import sys

from werkzeug.wrappers import Request, Response
import talisker
from talisker.util import module_cache, pkg_is_installed
from talisker.render import (
    Content,
    Head,
    Link,
    Table,
    render,
)


__all__ = ['private']
logger = logging.getLogger(__name__)


class TestException(Exception):
    pass


def force_unicode(s):
    if isinstance(s, bytes):
        return s.decode('utf8')
    return s


def info_response(request, title, *content):
    """Return a response rendered using talisker.render."""
    content_type = request.accept_mimetypes.best_match(
        ['text/plain', 'text/html'],
        default='text/plain',
    )
    return Response(
        render(content_type, Head(title), content),
        mimetype=content_type,
    )


PRIVATE_BODY_RESPONSE_TEMPLATE = """
IP address {0} not in trusted network.

REMOTE_ADDR: {1}
X-Forwarded-For: {2}
""".lstrip('\n')


def private(f):
    """Only allow approved source addresses."""

    @functools.wraps(f)
    def wrapper(self, request):
        config = talisker.get_config()
        if not request.access_route:
            # this means something probably bugged in werkzeug, but let's fail
            # gracefully
            return Response('no client ip provided', status='403')

        ip_str = force_unicode(request.access_route[-1])
        ip = ip_address(ip_str)
        if ip.is_loopback or any(ip in network for network in config.networks):
            return f(self, request)
        else:
            msg = PRIVATE_BODY_RESPONSE_TEMPLATE.format(
                ip_str,
                force_unicode(request.remote_addr),
                request.headers.get('x-forwarded-for'))
            return Response(msg, status='403')
    return wrapper


def ok_response():
    return Response(talisker.get_config().revision_id + '\n')


@module_cache
def test_counter():
    # this is created lazily as we may not have prometheus installed.
    # Also, isolate in its own registry. Multiprocess mode doesn't really use
    # registries, but it helps keep things separated, which is useful in
    # testing.
    from prometheus_client import Counter, CollectorRegistry
    return Counter('test', 'test', registry=CollectorRegistry())


class StandardEndpointMiddleware(object):
    """WSGI middleware to provide a standard set of endpoints for a service"""

    urlmap = collections.OrderedDict((
        ('', 'index'),
        ('/index', 'index'),
        ('/check', 'check'),
        ('/metrics', None),
        ('/ping', 'ping'),
        ('/info/config', 'config'),
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
        response = None
        if request.path.startswith(self.prefix):
            path = request.path[len(self.prefix):].rstrip('/')
            try:
                funcname = self.urlmap.get(path, None)
                func = getattr(self, funcname)
            except (KeyError, AttributeError, TypeError):
                pass
            else:
                response = func(request)

        if response is None:
            # pass thru to the app
            return self.app(environ, start_response)
        else:
            return response(environ, start_response)

    def index(self, request):
        methods = []
        base = request.host_url.rstrip('/')
        for url, funcname in self.urlmap.items():
            if funcname is None:
                continue
            if url in self.no_index:
                continue
            try:
                func = getattr(self, funcname)
            except AttributeError:
                pass
            else:
                methods.append((
                    Link(url, self.prefix + url, host=base),
                    str(func.__doc__),
                ))
        return info_response(
            request,
            'Status',
            Table(methods),
        )

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

        test_counter().inc()
        return Response('Incremented test counter')

    @private
    def metrics(self, request):
        """Endpoint exposing Prometheus metrics"""
        if not pkg_is_installed('prometheus-client'):
            return Response('Not Supported', status=501)

        from prometheus_client import CONTENT_TYPE_LATEST
        from talisker.prometheus import (
            collect_metrics,
            PrometheusLockTimeout,
        )

        try:
            data = collect_metrics()
        except PrometheusLockTimeout:
            msg = 'Failed to acquire prometheus lock to collect metrics'
            logger.exception(msg)
            return Response([msg], status=500, mimetype='text/plain')

        return Response(data, status=200, mimetype=CONTENT_TYPE_LATEST)

    @private
    def logtree(self, request):
        """Display the stdlib logging configuration."""
        import logging_tree
        tree = logging_tree.format.build_description()
        return Response(tree)

    @private
    def config(self, request):
        config = talisker.get_config()
        rows = []
        for name, meta in config.metadata().items():
            if meta.default is None:
                is_default = ''
            else:
                is_default = meta.default == meta.value

            rows.append((
                name,
                meta.value,
                '' if meta.raw is None else repr(meta.raw),
                is_default,
            ))

        return info_response(
            request,
            'Config',
            Content('Config', 'h2'),
            Table(rows, headers=['Name', 'Value', 'Raw Value', 'Is Default'])
        )

    @private
    def packages(self, request):
        """List of python packages installed."""
        import pkg_resources
        rows = []
        for p in sorted(
                pkg_resources.working_set, key=lambda p: p.project_name):
            rows.append((
                p.project_name,
                p._version,
                p.location,
                Link(
                    'PyPI',
                    'https://pypi.org/project/{}/{}/',
                    p.project_name,
                    p._version,
                ),
            ))

        return info_response(
            request,
            'Python Packages',
            Table(
                rows,
                headers=['Package', 'Version', 'Location', 'PyPI Link'],
            )
        )

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

        master = arbiter.as_dict(MASTER_FIELDS)
        master['cmdline'] = ' '.join(master['cmdline'])

        environ = master.pop('environ')
        config = talisker.get_config()
        clean_environ = [
            (k, v) for k, v in sorted(environ.items())
            if k in config.METADATA
        ]
        sorted_master = [(k, master[k]) for k in MASTER_FIELDS if k in master]

        return info_response(
            request,
            'Workers',
            Content('Workers', 'h2'),
            Table(rows, headers=HEADERS),
            Content('Process Information', 'h2'),
            Table(sorted_master),
            Content('Process Environment (whitelist)', 'h2'),
            Table(clean_environ),
        )

    @private
    def objgraph(self, request):
        import objgraph
        limit = int(request.args.get('limit', 10))
        types = objgraph.most_common_types(limit=limit, shortnames=False)
        leaking = objgraph.most_common_types(
            limit=limit,
            objects=objgraph.get_leaking_objects(),
            shortnames=False,
        )

        # html only links
        limits = [
            'Number of items: ',
            Link('{}', request.path + '?limit={}', 10).html(),
            Link('{}', request.path + '?limit={}', 20).html(),
            Link('{}', request.path + '?limit={}', 50).html(),
        ]
        return info_response(
            request,
            'Python Objects',
            Content(
                'Python Objects for Worker pid {}'.format(os.getpid()),
                'h1',
            ),
            Content(' '.join(limits), 'p', text=False, escape=False),
            Content('Most Common Objects', 'h2'),
            Table(types),
            Content('Leaking Objects (no referrer)', 'h2'),
            Table(leaking),
        )


MASTER_FIELDS = [
    'cwd',
    'cmdline',
    'exe',
    'uids',
    'gids',
    'terminal',
    'environ',
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
    return '{}MB'.format(x // (1024 ** 2))


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
