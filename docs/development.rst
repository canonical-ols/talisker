Development using Talisker
==========================

Talisker has been designed with the goal of working in development *and*
production. This is to try and encourage the same tool used throughout.

Talisker's default configuration is designed for production usage, e.g.:

 - only INFO level logs and above go to stderr
 - python's warning system is disabled


Devel Mode
----------

If stderr is a tty, Talisker will run in devel mode. Additionally, if the DEVEL
env var is set, it will run in devel mode.

What this means varies on which tool you are using, but at a base level it
enables python's warning logs, as you generally want these in development.

For Gunicorn, devel mode means a few more things:

 - enables access logs to stderr
 - sets timeout to 99999, to avoid timeouts when debugging
 - it enables auto reloading on code changes

Also, for convenience, it you manually set Gunicorn's debug level to DEBUG, when
in devel mode, Talisker will actually log debug level messages to stderr.


Development Logging
-------------------

Talisker logs have been designed to be readable in development.

This includes:

 - preserving the common first 4 fields in python logging for developer familiarity.

 - tags are rendered most-specific to least specific.  This means that the tags
   a developer is interested in are likely first.

 - if stderr is an interactive tty, then logs are colorized, to aid human reading.

