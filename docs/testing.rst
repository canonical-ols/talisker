.. highlight:: python

.. _testing:

=====================
Testing with Talisker
=====================

Talisker provides various tools to assist in unit testing application that use it's features.


Test suite integration
----------------------

In order to run your tests in the same configuration as production, you should
initialise Talisker for testing as early as possible in your test suite::

    talisker.testing.configure_testing()

This will set up Talisker logging with a logging.NullHandler on the root logger,
as well as configure the global sentry client to point to dummy remote to
capture sentry messages.

Talisker uses some module globals, thread locals, and request contexts to
store state. For unit tests, it is a good idea to ensure this state is
cleared between tests, or else tests can not be properly isolated. To do so,
ensure the following is run before every test::

    talisker.testing.clear_all()


Test Helpers
------------

Talisker provides a context manager for testing that will capture every log
message, sentry report and statsd metric generated while it is active. It
produces a test context that can be used to assert against these artefacts::

    with talisker.testing.TestContext() as ctx:
        # code under test

The context object collects events that happened while active, and presents
them for inspection::

    # ctx.statsd is an array of statsd metrics as strings
    self.assertEqual(ctx.statsd[0], 'some.metric:1.000000|ms')

    # ctx.sentry is an array of sentry messages sent, as the JSON dict that was
    # sent by the sentry client
    self.assertEqual(ctx.sentry[0]['message'] == 'my message')

    # ctx.logs is a talisker.testing.LogRecordList, which is essentially a list
    # of logging.LogRecords
    self.assertTrue(ctx.logs[0].msg == 'my msg')


The *logs* attribute instance also provides some convenience APIs, *filter()*,
*exists()* and *find()*::

    my_logs = ctx.logs.filter(name='app.logger')
    self.assertEqual(len(my_logs) == 2)
    self.assertTrue(my_logs.exists(
        level='info',
        msg='my msg',
        extra={'foo': 'bar'},
    ))
    warning = my_logs.find(level='warning')
    self.assertIn('baz', warning.extra)


These APIs will search logs that match the supplied keyword arguments, using
the keyword to look up the attribute on the logging.LogRecord instances.
A full list of such attributes can be found here:

https://docs.python.org/3/library/logging.html#logrecord-attributes

For all these APIs, the following applies:

 * The 'level' keyword can be a case insensitive string or an int (e.g. 'info'
   or logging.INFO), and the appropriate LogRecord attribute (levelname or
   levelno) will be used.

 * The 'msg' keyword is compared against the raw message. The 'message' keyword
   is compared against the interpolated msg % args.

 * Matching for strings is contains, not equality, i.e. *needle in haystack*, not just *needle
   == haystack*.

 * The extra dict is special cased: each supplied extra key/value is checked
   against the *LogRecord.extra* dict that Talisker adds.

 * *filter()* returns a LogRecordList, so is chainable.

 * *find()* returns the first LogRecord found, or None.

 * *exists()* returns True if a matching LogRecord is found, else False


