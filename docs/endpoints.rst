.. highlight:: python



================
Status Endpoints
================

Talisker provides a set of app-agnostic standard endpoints for your app for
querying its status. This is designed to that in production you have standard
ways to investigate problems, and to configure load balancer health checks and
nagios checks.


``/_status/ping``
    A simple check designed for use with haproxy's httpcheck option, returns
    200, responds to GET, HEAD, or OPTIONS, the body content being the
    application's Revision_.

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

``/_status/info``
    Return some useful information about server status (TODO).

.. _revision:

Revision
--------

It is often useful to know what revision of your software is running, either
for manual checking, or automatic deploy tooling. Talisker returns this in body
of a ``/_status/ping`` request, and also adds it to every response with the header
X-VCS-Revision:

Talisker does it's best to figure out the revision of your code. It tries the
following methods to discover the revision.

  * output of 'git rev-parse HEAD'
  * output of 'bzr revno'
  * bzr `versio-ninfo
    <http://doc.bazaar.canonical.com/beta/en/user-reference/version-info-help.html>`_:
    versioninfo.version_info['revno']
  * output of 'hg id -i'

If falls back to string 'unknown' if none of the above work.

To supply a custom revision, call the following in your startup code:::

  talisker.revision.set(my_revision)


