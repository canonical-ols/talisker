from __future__ import absolute_import, division, print_function
from werkzeug.wrappers import Request, Response


app_data = {
    'version': None,
    'active': True,
}


def set_version(version):
    app_data['version'] = version


def signal_restart():
    """Signal to haproxy we are restarting, via 404 on the haproxy check."""
    app_data['active'] = False


class TestException(Exception):
    pass


class StandardEndpointMiddleware(object):
    """WSGI middleware to provide a standard set of endpoints for a service"""

    _ok = Response('OK')

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
        for name, func in self.__class__.__dict__.items():
            if not name.startswith('_') and name != 'index':
                methods.append(item.format(name, func.__doc__))
        return Response(
            '<ul>' + '\n'.join(methods) + '<ul>', mimetype='text/html')

    def haproxy(self, request):
        """HAProxy status check"""
        if app_data['active']:
            return self._ok
        else:
            # for use with haproxy's http-check disable-on-404 option, to
            # take the server out of the farm pre-emptively
            return Response('biab, lol', status=404)

    def nagios(self, request):
        """Nagios health check"""
        start_data = {}
        status = headers = None

        def nagios_start(status, headers, exc_info=None):
            # save status for inspection
            start_data['status'] = status
            start_data['headers'] = headers

        response = self.app(request.environ, nagios_start)
        if start_data['status'].startswith('404'):
            # app does not provide /_status/nagios endpoint
            return self._ok
        else:
            # return app's response
            return Response(response, status=status, headers=headers)

    def version(self, request):
        """Version currently deployed on this service"""
        version = app_data['version']
        return Response('unknown' if version is None else version)

    def error(self, request):
        """Raise a TestError for testing"""
        raise TestException('this is a test, ignore')

    def metric(self, request):
        return Response('Not Implemented', status=501)

    def info(self, request):
        return Response('Not Implemented', status=501)
