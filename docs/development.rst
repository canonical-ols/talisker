Development using Talisker
==========================

Talisker has been designed with the goal of working in development *and*
production. This is to try and encourage the same tool used throughout.

Talisker's default configuration is designed for production usage, e.g.:

 - only INFO level logs and above go to stderr
 - python's warning system is disabled


DEVEL Mode
----------

If the DEVEL env var is set, Talisker will run in DEVEL mode.

What this means varies on which tool you are using, but at a base level it
enables python's warning logs, as you generally want these in development.

For Gunicorn, DEVEL mode means a few more things:

 - enables access logs to stderr
 - sets timeout to 99999, to avoid timeouts when debugging
 - it enables auto reloading on code changes

Also, for developer convenience, if you manually set Gunicorn's debug level to DEBUG, when
in DEVEL mode, Talisker will actually log debug level messages to stderr.


Development Logging
-------------------

Talisker logs have been designed to be readable in development.

This includes:

 - preserving the common first 4 fields in python logging for developer familiarity.

 - tags are rendered most-specific to least specific.  This means that the tags
   a developer is interested in are likely first.

 - if stderr is an interactive tty, then logs are colorized, to aid human reading.


Colored Output
--------------

If in DEVEL mode, and stdout is a tty device, then Talisker will colorise log output.

To disable this, you can set the env var:

.. code-block:: bash

    TALISKER_COLOR=no

The colorscheme looks best on dark terminal backgrounds, but should be readable on
light terminals too.

If your terminal doesn't support bold, dim, or italic text formatting, it might
look unpleasent. In that case, you can try the simpler colors

.. code-block:: bash

    TALISKER_COLOR=simple
