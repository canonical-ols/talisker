import pprint
import werkzeug.serving
import talisker.wsgi


def reflect(environ, start_response):
    status = '404 Not Found'
    start_response(status, [('content-type', 'text/plain')])
    return status + '\n\n' + pprint.pformat(environ)

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    app = talisker.wsgi.wrap(reflect)
    run_simple('0.0.0.0', 5000, app, use_debugger=True, use_reloader=True)
