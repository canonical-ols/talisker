0.19.0 (2020-09-07)
-------------------

* Fix proxy config application to backends in TalikerAdapter (#534)
* Require contexts to be explicitly created. (#543)

Note: this change means that there is no default context. This fixes a number
of issues with context existing in non-request/job code (e.g. startup code,
gunicorn master process).

0.18.0 (2020-04-17)
-------------------

* Add support for Python 3.8 and gevent 1.5.0 (#515)
* support latest prometheus-client, and raise minimum supported version to 0.5 (#516)
* fix missing rogue import (#517)
* Fix unbound local variable on request timeout. (#512)

0.17.0 (2020-04-08)
-------------------

* Fix the sdist builds so that they include setup.py /o\

Sadly, many previous sdists are broken, and PyPI does not allow reuploading, so
there is no real fix :(

0.16.1 (2020-04-02)
-------------------

* bumped supported version of werkzeug to <=1.2

0.16.0 (2020-03-04)
-------------------

*  support gunicorn 20.x (#502)
*  Add EXPLAIN output to sql sentry breadcrumbs (#499)
*  Support X-Debug header that sends sentry report (#498)
*  Better gunicorn timeout handling. (#497)
*  Defer sentry reports until after request complete. (#496)
*  Sentry logging breadcrumb fixes (#493)
*  refactor wsgi request logging, so that we will have more information available (#492)

0.15.0 (2019-07-25)
-------------------

* support latest flask and werkzeug releases (#472)
* Support per-request deadlines in network stack (#469)
* Add TALISKER_STATUS_INTERFACE config to restrict bind to interface
* Use contextvars for request context

0.14.3 (2019-04-24)
-------------------

* Fix lazy responses that have no content (#447)
* Fix importing issues with talisker.run (#442)

0.14.2 (2019-03-29)
-------------------

* Change requests.TaliskerAdapter to require scheme (#435)
* Do not assume requests Connection error always wraps a urllib3.Retry error. (#434)

0.14.1 (2019-03-21)
-------------------

* Fix no content responses by still trying to call start_response() early (#431)

0.14.0 (2019-03-18)
-------------------

* Make raven an optional dependency (#429)
* properly support super lazy WSGI apps, like werkzeug's debugger

0.13.0 (2019-03-08)
-------------------

* Make gunicorn an optional dependency
* Fix use of werkzeug debugger

0.12.0 (2019-02-22)
-------------------

This release includes a fair amount of internal refactoring, and some new features.

* Logs and metrics for timeouts in gunicorn (#412)
* Errors are now handled in WSGI, and return text/html/json per Accept header (#409)
* Soft timeouts are sent after the request is finished (#411)
* Add requests.TaliskerAdapter, a requests transport adapter with loadbalancing and retries (experimental, #405, #408)
* Move logging from gunicorn into WSGI middleware (#402)
* Don't use raven's WSGI middleware, do it in our middleware (#406)
* All /_status/info/ endpoints support rendering JSON as well as text and HTML (#407)
* support rendering json responses as well as text and html (#407)
* move the request-id header name to config (#401)
* fix requests latency buckets (#413)

0.11.1 (2019-01-09)
-------------------

* add additional sanitised keys by default, and add config for additional keys. Requires raven 6.4 (#392)
* fix parsing of extra['start_time'] being a string in recent raven (#390)

0.11.0 (2018-12-18)
-------------------

This release fixes an accidental hard dependency on celery that was added in 0.10.0.

The main feature is refactor of Talisker configuration, which now allows for
using a config file as well as environment variables. It also provides
consistant documentation for all configuration in a single place, and a new
talisker.help cli tool, and a new /_status/info/config endpoint for introspection.

* Add documentation for config, including new talisker.help command (#386)
* Ensure optional extras are actually optional (#385)
* Improve config error handling and logging of errors. (#382)
* Add centralised config, with config file support (#380)

0.10.2 (2018-11-29)
-------------------

* Add companion TestContext.assert_not_log to match assert_log

0.10.1 (2018-11-26)
-------------------

* Add assert_log helper to TestContext (#377)
* Fixed where some classes where accidentally old-style classes in python 2

0.10.0 (2018-11-20)
-------------------

* Add a public testing helper (testing.talisker.TestContext), to isolate and collect talisker data in tests (#329)
* Expose new talisker.testing.clear_all() api to make it easier to reset talisker state in (#328)
* Add a timeout for prometheus locks, and asupport non-blocking locking in gevent (#358)
* Do not enable prometheus multiprocess mode if there is only one gunicorn worker (#358)
* Remove username/email from any user data in sentry (#342)
* Add a relative-to-request start timestamp to all sentry breadcrumbs. (#340)
* Support prometheus 0.4+ (#334)

0.9.16 (2018-10-02)
-------------------

* Improve the ip->name mapping for requests metric names (#304)
* improve sentry report metadata, add tags and also sql statement summary (#306)
* Track per-request sql/http/log costs (#325)
* add explicit context clears at various points (#305)
* TERM=dumb turns off terminal colors

0.9.15 (2018-09-12)
-------------------

* Support statsd 3.3 (#290)
* Properly serialize the prometheus worker cleanup (#296)
* Gracefully fail if lock can't be initialised (#303)

0.9.14 (2018-08-21)
-------------------

A collection of minor improvements and fixes, and relicensing to Apache 2.

* Relicense to Apache-2 (#258, #275) (thanks to Adam Collard)
* Aggregate prometheus metrics into one file on worker death. (#281, #288)
* Wrapping logging and metrics code with try/except, so that we never fail (#276)
* Fail more gracefully in the case where talisker has not been setup properly (#264)
* Add support for TALISKER_REVISION_ID variable (#262) (thanks to Robin Winslow and Adam Collard)
* Return sentry id from capture (#261)
* Set level=warning in soft req. timeout sentry messages (#255) (thanks to Guillermo Gonzalez)

0.9.13 (2018-07-04)
-------------------

* Fix X-Request-Id to be a native string on py2 (#247)

0.9.12 (2018-06-20)
-------------------

* only set prometheus envvar in gunicorn runner, not for all runners (#242)

0.9.11 (2018-06-18)
-------------------

* Fix a regression that broke prometheus metrics in multiprocess environments.

0.9.10 (2018-06-07)
-------------------

* Change default slow query threshold to -1 even in DEVEL (#226)
* Move the clearing of various request contexts as late as possible (#233)
* add soft request timeout support (#231) - thanks to Guillermo Gonzalez
* support raven 6.9.0 (#232) - thanks to Guillermo Gonzalez

0.9.9 (2018-05-21)
------------------

This release collects a number of bugfixes

 * Make parsing the postgres dsn more robust (#224)
 * Protect django middleware view introspection (#220) (thanks to tomwardill)
 * Ensure that configured sentry processors is a set (#219) (thanks to tomwardill)
 * Fix link escaping in objgraph page (#217)

0.9.8 (2018-05-10)
------------------

The main feature in this release is new endpoints for debugging (#213):

* /_status/info/packages: show a list of installed python packages and versions
* /_status/info/workers: show resource usage of gunicorn workers, and general process infomation [requires psutil]
* /_status/info/objgraph: show python object counts and potential leaks [requires objgraph]

These endpoints are IP restricted to TALISKER_NETWORKS, and can render as text via curl or html via browser.

* Renamed all structured logging fields called "duration" to "duration_ms" to indicate units (#215)
* Unknown /_status/ urls are passed through to app, to allow for 404 format control by the app (#212)
* We only quote logfmt stings if needed, reduces visual noise on log lines (#173)
* DEVEL colorscheme improved to support light terminals, and a simpler option that doesn't use italics or bold (#188)
* log request size/type in gunicorn logs (#174)
* Added support for flask 1.0 and prometheus client 0.2, make django 1.10 the minimum supported version (#209, #198)

0.9.7 (2018-03-28)
------------------

The main work in this release has been improvments to metrics.

* Collect prometheus metrics as well as statsd for gunicorn, requests, and celery (#172)
* Support flask/django adding X-View-Name header to indicate view function (#151)
* Control over naming requests metrics (#171)
* Gunicorn logging enhancements (#165)
* Gather better metadata from OSError exceptions
* Fixed some small logging issues

0.9.6 (2018-02-21)
------------------

* The logfmt output has been reworked to explictly quote strings, and test
  coverage much improved in the process.  This allows for more robust parsing
  in logstash, such as allowing numeric fields.

* New talisker.testing module, which has helpers for functionally testing
  talisker servers and related talisker tools.

* Added a functional test suite using the new talisker.testing helpers

* Custom ruby logstash filter to handle parsing of numeric values and escaped quotes.

0.9.5 (2017-05-23)
------------------

* add support for postgresql via psycopg2 (#85). This will add breadcrumbs to
  sentry reports, as slow query logs.
  See http://talisker.readthedocs.io/en/latest/postgresql.html for more info

* Access log cleanups (#94). We no longer include the querystring in the
  logmsg, just as a field.

* Improved proxy handling in private endpoints. (#92). Fixes X-Forwarder-For handling.

* Clear sentry context on request start (#90). This stops some breadcrumbs
  bleeding between requests.

* Fix sentry default config when used with flask (#89). This was causing
  release tag to not be applied to sentry reports.

* truncate long log messages (#86). This prevents DOSing logstash.


0.9.4 (2017-04-25)
------------------

* require explicit DEVEL env var to enable colored output.

* Add ability to force switch colors off with TALISKER_COLOR=no

* Fix bug in grok filter to allow _ in logger name

* Drop log tags that are empty, as logstash can't cope with them

* Truncate very long log messages and tags (at 10k/2k respectively) to avoid accidental DOS.

0.9.3 (2017-04-13)
------------------

* Fix gunicorn logger metrics and logging, adding tests (#75)

0.9.2 (2017-04-11)
------------------

Bug fix release

* Fix celery metrics with eager tasks (#70)
* Fix statsd cli args and metric format (#71)
* Also fix depencecies on recent setuptools

0.9.1 (2017-03-23)
------------------

This release has a couple of important bugfixes, upgrading is strongly encouraged.

* Feature: Add a generic script runner to run any python script with
  talisker logging, primary usecase is django managment commands:

    talisker.run myscript.py ...

* Improvement: DEVEL env var is no longer required (although still respected).
  Talisker will assume DEVEL mode when stderr is a tty.

* Bugfix: re-add http metrics for gunicorn which were accidentaly dropped in
  a refactor, with regression tests

* Bugfix: fix celery integration with 3.1.13+, with regression tests

* Bugfix: Add missing request_id to new accesslogs

* Bugfix: Fix issue #35, respect --log-level for gunicorn in DEVEL mode. This
  means you can do --log-devel=debug and get debug level logging to your
  console.

* Improvement: support raven 6

* Testing: now testing against pypy in CI, and also agains the minimum
  supported versions of various dependencies too, to help prevent further
  accidental dependencies on latest version apis (which is what broke celery
  3.1.x integration)


0.9.0 (2017-01-24)
------------------

The major feature in this release is support for sentry, which is integrated
with wsgi, logging, and celery. Also supports opt-in integration with
flask and django, see the relevant docs for more info.

Other changes

 * refactor of how logging contexts were implemented. More flexible and
   reliable. Note `talisker.logs.extra_logging` and
   `talisker.logs.set_logging_context` are now deprecated, you should
   use `talisker.logs.logging_context` and
   `talisker.logs.logging_context.push`, respectively, as covered in the
   updated logging docs.

 * improved celery logging, tasks logs now have task_id and task_name
   automatically added to their logs.

 * improved logging messages when parsing TALISKER_NETWORKS at startup


0.8.0 (2016-12-13)
------------------

* prometheus: add optinal support for promethues_client
* celery: request id automatically sent and logged, and support for 4.0
* docs: initial 'talisker contract'
* statsd: better client initialisation
* internal: refactoring of global variables, better /_status/ url dispatch

0.7.1 (2016-11-09)
------------------

* remove use of future's import hooks, as they mess with raven's vendored imports
* slight tweak to logfmt serialisation, and update docs to match

0.7.0 (2016-11-03)
------------------

*Upgrading*

This release includes a couple of minor backwards incompatible changes:

1) access logs now use the talisker format, rather than CLF. See the docs for
   more info. If you are using access logs already, then the easiest upgrade
   path is to output the access logs to stderr (access_logfile="-"), and delete
   your old log files.

2) talisker no longer prefixes developer supplied tags with 'svc.'. This should
   only matter if you've already set up dashboards or similar with the old
   prefixed name, and you will need to remove the prefix

Changes:

  * access logs now `in logfmt
    <http://talisker.readthedocs.io/en/latest/logging.html#gunicorn-logs>`_
    rather than CLF

  * dummy statsd client is now useful `in testing
    <http://talisker.readthedocs.io/en/latest/statsd.html#testing>`_

  * logs are colored in development, to aid reading

  * the 'svc' prefix for tags has been removed

0.6.7 (2016-10-05)
------------------

* actually include the encoding fix for check endpoint

0.6.6 (2016-10-05)
------------------

* add celery metrics
* fix issue with encoding in check endpoint when iterable

0.6.5 (2016-09-26)
------------------

* make celery runner actually work, wrt logging

0.6.4 (2016-09-23)
------------------

* fix encoding issue with X-Request-Id header (again!)

0.6.3 (2016-09-21)
------------------

* fix setuptools entry points, which were typoed into oblivion.

0.6.2 (2016-09-21)
------------------

* make gunicorn use proper statsd client
* log some extra warnings if we try to configure gunicorn things that talisker
  overides.
* better documented public api via __all__
* first take on some celery helpers
* some packaging improvements

0.6.1 (2016-09-12)
------------------

* actually do remove old DEBUGLOG backups, as backupCount=0 does not remove
  any. Of course.

0.6.0 (2016-09-09)
------------------

* Propagate gunicorn.error log, and remove its default handler.

This allows consistant logging, making the choice in all cases that your
gunicorn logs go to the same stream as your other application log, making the
choice in all cases that your gunicorn logs go to the same stream as your other
application logs.

We issue a warning if the user tries to configure errorlog manually, as it
won't work as expected.
