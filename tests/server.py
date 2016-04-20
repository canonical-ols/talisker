import pprint


def application(environ, start_response):
    status = '404 Not Found'
    start_response(status, [('content-type', 'text/plain')])
    s = environ['statsd']
    statsd = 'statsd: {} {}'.format(s._addr, s._prefix)
    output = (status + '\n\n' +
              statsd + '\n\n' +
              pprint.pformat(environ))

    return output.encode('utf8')
