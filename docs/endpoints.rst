
================
Status Endpoints
================

Talisker provides a set of app-agnostic standard endpoints for your app for
querying its status. This is designed so that in production you have standard
ways to investigate problems, and to configure load balancer health checks and
nagios checks.


``/_status/ping``
    A simple check designed for use with haproxy's httpcheck option, returns
    200, responds to GET, HEAD, or OPTIONS, the body content being the
    application's revison

``/_status/check``
    For use with nagios check_http plugin, or similar.

    It tries to hit ``/_status/check`` in your app. If that is not found,
    it just returns a 200, as a basic proxy for the application being up.

``/_status/test/sentry`` (``/_status/error`` for backwards compatibility)
    Raise a test error, designed to test sentry/raven integration.

``/_status/test/statsd``
    Send a test metric value. Designed to test statsd integration.

``/_status/test/prometheus``
    Increment a test counter. Designed to test Prometheus integration.

``/_status/metrics``
    Exposes prometheus metrics in Prometheus text format.

``/_status/info/config``
    Shows the current Talisker configuration

``/_status/info/packages``
    Shows a list of installed python packages and their versions

``/_status/info/workers``
    Shows a summary of master and worker processes (e.g CPU, memory, fd count)
    and other process information.  *Only available if psutil is installed.*

``/_status/info/objgraph``
    Shows the most common python objects in user for the worker that services
    the request.  *Only available if objgraph is installed.*

``/_status/info/logtree``
    Displays the stdlib logging configuration using logging_tree.  *Only
    available if logging_tree is installed.*

