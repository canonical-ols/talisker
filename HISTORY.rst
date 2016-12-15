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

0.5.7 (2016-09-02)
------------------

* Update publishing workflow
* Add make changelog target

0.5.6 (2016-09-02)
------------------

* more testing release process in prepartion for 0.6

0.5.5 (2016-09-02)
------------------

* testing release process in prepartion for 0.6

0.5.4 (2016-08-10)
------------------

* series of point release to fix various small bugs

0.5.0 (2016-08-10)
------------------

* add grok filters for logstash
* slight adjustment to logfmt serialisation: talisker now strips " from tag
  values. This is due to a limitation in logstash.

0.4.1 (2016-08-05)
------------------

* publish separate py2/py3 wheels, due to dependency differences
* some doc changes

0.4.0 (2016-08-05)
------------------

* First public release an PyPI.
