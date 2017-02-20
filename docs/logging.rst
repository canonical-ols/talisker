.. highlight:: python

=======
Logging
=======

Talisker configures a specfic carefully designed logging set up. At a high
level, it configures the following with the stdlib logging module:

 - logger class that can collect structured data
 - formatter that supports structured data via logfmt
 - root handler that logs everying at INFO level to stderr

Talisker also provides additional debuging options that can be used for more information.

The stdlib logging module is old, based on a Java API, and makes heavy use of
global state. Some of the implementation details for talisker are work arounds
for these limitations. But stdlib logging is everywhere, and is actually very
flexible, so we can make it work how we want to.


Configuring Logging
-------------------

If you use Talisker's entry points, like `talisker.gunicorn` or
`talisker.celery`, then logging will be configured by default.

You can also use the more generic entrypoints that talisker provides to run any
script with Talisker logging enabled.

.. code-block:: bash

    talisker.run script.py ...

or

.. code-block:: bash

    python -m talisker script.py ...


If you are using your own entry point, you can configure Talisker with::

    import talisker
    talisker.initialise()

Note that this should be done *before* any loggers are created via
`logging.getLogger()` or similar, as they will not be altered.


This will set up logging, taking into account environment variables
like DEVEL and DEBUGLOG. If you want to configure those parameters
explcitly, you can do::

    talisker.logs.configure_logging(devel, debug)

For testing, you can use special test configuration, which sets up
talisker style logging, except adds a single NullHandler to the root
logger::

    talisker.logs.configure_test_logging()

This means logging will work as per talisker's set up, but you will get
no log output. You can always add a logging.handlers.BufferdHandler
temporarily to capture log messages in tests, e.g. for pytest::

    import pytest
    @pytest.fixture
    def log():
        handler = logging.handlers.BufferingHandler(10000)
        try:
            logs.add_talisker_handler(logging.NOTSET, handler)
            yield handler.buffer
        finally:
            handler.flush()
            logging.getLogger().handlers.remove(handler)

and use like so::

    def test_something(log):
        something()
        # log is a list of logging.LogRecord items
        assert type(log[0]) is logging.LogRecord


Logger Class
------------

Talisker sets a custom base logger class via logging.setLoggerClass(). It's only
difference to logger.Logger is that it supports more explicitly storing 'extra'
arguments to the log call. This allows the StructuredFormatter class to append
an arbitrary number of flags to the formatted message. Without this, there is
no way to know which fields of a LogRecord are supposed to be added as tags.

It also supports pulling in additional `extra` data from the current context,
which is primarily used for providing request_id data for the log message.


Root Handler
------------

Talisker simply adds a handler to the root logger to log to stderr, at the INFO
log level.

 * Simple, self-contained application, no log file config
 * No file permissions needed by app
 * System handles buffering, synchronisation, persistance, rotation and shipping
 * Works in development
 * PaaS friendly


.. sidebar::  A note about log levels

  Go read Dave Cheney's excellent post `Let's talk about logging
  <http://dave.cheney.net/2015/11/05/lets-talk-about-logging>`_. It's focus is
  on golang logging, but is universally applicable.

  There are two intended users of logs: users and developers.  In a WSGI
  service setting the user is someone in an operations role, trying to debug
  something in a production setting, where security and scale preclude logging
  everything. This is the INFO level. There is no need for anything more really
  (as argued in the post above), but this will of course include any logs at
  a higher level, as many libraries do use those levels. Anything going to
  stderr is designed to be shipped, so log with that in mind, regarding PII or
  secrets.

  Note, if you put sensitive information as an 'extra', then its easier for
  your log shipping/aggregation tool to mask. But, perhaps it is better not to
  log it the first place, or only at DEBUG level?


Debug Logging
-------------

Talisker also supports adding an additional root handler that logs to disk at
DEBUG level. The stderr logging output is unchanged.

To enable, just set the DEBUGLOG envvar to the path you want the log file to go
to::

  DEBUGLOG=/path/to/logfile talisker ...

If talisker can open that file, it will add a handler to log to it at DEBUG
level, and log a message at the start of your log output to say it is doing do.
If it cannot open that file, it will log a message saying so, but not fail.
The handler is a TimedRotatingFileHandler, set to 24 hour period with no backup
copies, i.e. logs last for 24 hours at most.

This is designed to support development and production use cases.

In development, typically usage of DEBUG logs is via a greping a file, rather
than viewing in the console, given the verbosity. So we write to disk where the
developer has told us to, and they can grep/view the file there.

In production, operators sometimes want to turn on more logging for limited
period, to debug a specfic problem. But we generally don't want to ship that
extra logging. This is in part due to scaling - debug logs can be 10x more
verbose than INFO, this could lead to a 10x traffic spike on your log
aggregation service.  Additionally, debug logs often include details that are
sensitive, and you don't want stored centrally. So this mechanism of writing to
a temporary log file helps in that scenarion too, as the INFO logging on stderr
that is shipped is unchanged.


Log Format
----------

Talisker uses a default format that is designed to be human readable in
development, but still structured for richer data.

.. sidebar:: Why hybrid format?

  Why not just use json in production, and text in dev?

  The motiviation for the hybrid format is to have one format used in
  both development and production. This means when developers look at
  on-disk logs in production, they look familiar and are readable. This
  is a opposed to json or similar.

  Now, in actual production, this should be rare, as developers should
  really be using a log aggregation tool like Kibana to view the logs.
  However, we have found that when developing our infrastructure-as-code
  locally, we don't have a full ELK stack to process logs, so we have to
  fall back to on disk logs on the actually machines to debug issues, so
  this feature is very useful then.


The talisker logging format is as follows::

    format = '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"'
    datefmt = "%Y-%m-%d %H:%M:%S"

which should look like this::

  2016-07-14 01:02:03.456Z INFO app "hello"

This provides:

 * the default data python logging usually has
 * a more ISOish timestamp (uses . for msecs rather than , but we omit the T for readability)
 * explicit UTC timestamps (logging module uses local time by default /o\)
 * explicitly quoted message (embedded " are escaped)

Talisker can also append an arbitrary number of 'tags' on the end of the log
line, following the `logfmt <https://brandur.org/logfmt>`_ idea. e.g.::

  2016-07-14 01:02:03.456Z INFO app "hello" foo=bar baz="some value"

.. sidebar:: Defining logfmt

    logfmt is very loosely specified, and our target parser has some limitations,
    so we define it as:

    * keys: any string, except:
        - `` ``, ``.``, and ``=`` are replaced by ``_``
        - ``"`` is replaced by ``""``
        - always unquoted in log message

    * values: any string, not quoted by default
        - if contains whitespace or ``=``, will be double quoted
        - ``"`` is replaced by ``""``

    Both keys and values can be of arbitrary length, and either utf8 encoded
    bytes, or unicode. Talisker will always encode the output in utf8.

    The reason for stripping " characters is to do with the limitations of
    logstash's kv filter, which cannot currently cope with them, even when
    escaped. See `issue 2
    <https://github.com/logstash-plugins/logstash-filter-kv/issues/2>`_ for
    more info. If this issue is fixed, talisker may in future escape
    " characters in values rather than strip them.

These extra tags can be specified in 2 main ways:

  1. By the developer at the call site::

         logger.info('something happened', extra={'foo': 'bar', 'context': 'I can haz it'})

       would output::

         2016-01-13 10:24:07.357Z INFO app "something happened" foo=bar, svc.context="I can haz it"

  2. For a specific context, e.g. for a request. Talisker uses this to add
     request_id to every log message for a specific request. e.g.::

         logger.info('something happened')

     would output::

         2016-01-13 10:24:07.357Z INFO app "something happened" request_id=<request id>

     You can add your own temporary context variables with a context manager::

         with talisker.logs.logging_context(foo="bar"):
             logger.info('my important message')

     would output::

         2016-01-13 10:24:07.357Z INFO app "my important message" foo=bar


Additionally, it would be expected that your log shipper should add
additional tags, like hostname or service group, to the logfmt tags when
shipping.

If there are any global or context keys, these will take precedence if there is
a collision with developer supplied keys. The developer keys will be suffixed
with a '_' to preserve the info, with out stomping on the other keys.

Log Supression
--------------

By default, talisker suppresses some loggers.

The python python py.warnings logger is set not to propagate, as these are just
noise in production.

Additionally, talisker also configures the 'requests' logger to WARNING level.
This is because the INFO level on requests is particularly verbose, and we use
requests everywhere.

If you prefer to have full requests logs, you can simply set the level yourself.

e.g.::

  logging.getLogger('requests').setLevel(logging.INFO)


Additional logging configuration
--------------------------------

Talisker just sets a root handler with formatter. You are free to add
your own additional loggers and handlers as needed via the normal
methods, if you need to.

You can still benefit from the structured logging provided by talisker if you
set your handler's formatter to be an instance of
talisker.logs.StructuredFormatter. This is a standard formatter, except it uses
UTC for the time and adds the logfmt tags on the end. The default format is as
specified in `Log Format`_.

For example, suppose you want to enable debug logs for django's db logger.

e.g::


  handler = logging.FileHandler('db.log')
  handler.setFormatter(talisker.logs.StructuredFormatter())
  handler.setLevel(logging.DEBUG)
  db = logging.getLogger('django.db.backends')
  db.setLevel(logging.DEBUG)
  db.setHandler(handler)


Development
-----------

Talisker has been designed to be used in development.

The log format is readable in development. Only developer added tags (via the
extra arg to logging calls) are added. If a request id header is present,
it will also be logged. Most additional tags are added in production.

Additionally, you can set the DEVEL environment varible. If present, talisker does the following:

 - disables suppression of warnings
 - configures gunicorn with dev options:
     - to reload when files change (--reload)
     - long timeouts for debugging (--timeout=99999)
     - access logs to stdout (--access-logfile=-)
     - manually supplied cli args will override, these are just defaults


See `Debug Logging`_ for info on how to enable more logging.


Gunicorn Logs
-------------

Gunicorn's error logs use taliskers logging setup.

Gunicorn's access logs use the same format, but are disabled by default, as per
gunicorn's defaults. The reasons for using the talikser format are:

 1) Can use the same log shipping/aggregation (e.g. grok filter)
 2) Can mix access logs and error logs in same stream.

To enable access logs on stderr, with the the error logs, use the normal gunicorn method:

.. code-block:: bash

  $ talisker --access-logfile=-

To log to a file:

.. code-block:: bash

  $ talisker --access-logfile=/path/to/file


Talisker overrides some config options for gunicorn, mainly to do with
logging. It issues warnings if the user specifies any of these configs,
as they will no be applied. Specifically, the following gunicorn config
items are ignored by talisker:

* --error-logfile/--log-file, as talisker logs everything to stderr

* --log-level, INFO is sent to stderr, and DEBUG level can
  be access via DEBUGLOG - see `Debug Logging`.

* --logger-class, talisker uses its custom class

* --statsd-host and --statsd-port, as talisker uses the
  STATSD_DSN env var.



Grok filters
------------

Talisker includes a filter and patterns for parsing the logformat into logstash
with grok. These are in the talisker/logstash/ directory of the source tree.
They are also included in the python package as resources.


RSyslog
-------

TODO

Django
------

TODO
