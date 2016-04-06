.. highlight:: python

========
Features
========


Logging
-------


This module provides a standard default way to do logging in python
apps. It aims to default to a production set up, but still be developer
friendly.


  1. Log to stderr.

     * Simple, self contained application, no log file config
     * System writes to disk, process user doesn't need write perms
     * System handles logrotate
     * Works as a good default in dev.
     * PaaS friendly


  2. Structured Logging Format

     * Defaults to::

         '%(asctime)s %(level)s %(name)s "%(message)" a=b c=d ...'

     * preserves familiar dev friendly format
     * adds arbitrary key value pairs, according to logfmt standard
     * tags set at process level, context/request level, or per call
     * A service name tag is required upon initial configuration


Warnings
--------

We silence py.warnings logger by default. If debug mode is enabled, they
are logged, but 'bare', i.e no tags or formatting, just the warning.


Gunicorn
--------

Talisker works as a drop in replacment for the standard gunicor runner, by and
large. See Usage_ for more info.

It configures gunicorns logging for you, which provides higher (ms) resolution
timestamps and includes request duration in the access log. It also configures
gunicorns error logs to use the standard log format.



Endpoints
---------

Talisker provides a set of standard endpoints for your app


/_status/haproxy
    A simple check for use with haproxy's httpcheck option, returns 200, responds
    to GET, HEAD, or OPTIONS.

    Optionally, you can set it to temporarily return 404, for use with
    disable-on-404 option, for better control over graceful restarts.::

        talisker.signal_restart()

/_status/nagios
    For use with nagios check_http plugin.

    It tries to hit `/_status/nagios` in your app. If that is not found, it just returns a 200


/_status/version
    Return the version of the service, defaults to 'unknown' Can be set with::

        talisker.set_version(version_string_or_dict)

/_status/error
    Raise a test error, designed to test sentry/raven integration

/_status/metric
    Send a test metric value. Designed to test statsd integration

/_status/info
    Return some useful information about server status.
