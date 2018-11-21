.. highlight:: python

.. _testing:

=====================
Testing with Talisker
=====================

Taliser provides various tools to assist in unit testing application that use it's features.


Test suite integration
----------------------

In order to run your tests in the same configuration as production, you should
initialise talisker for testing as early as possible in your test suite::

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
produces a test context that can be used to assert against these artifacts::

    with talisker.testing.TestContext() as ctx:
        # code under test

The context object collects events that happened while active, and presents
them for inspection::

    # ctx.statsd is an array of statsd metrics as strings
    self.assertEqual(ctx.statsd[0], 'some.metric:1.000000|ms')

    # ctx.sentry is an array of sentry messages sent, as dicts
    self.assertEqual(ctx.sentry[0]['id'] == 'some id')

    # ctx.logs is a talisker.testing.LogRecordList, which is essentially a list
    # of logging.LogRecords
    self.assertTrue(ctx.logs[0].msg == 'my msg')

    # it also provides a convienience api
    self.assertTrue(ctx.logs.exists(
        name='app.logger',
        msg='my msg',
        extra={'foo': 'bar'},
    ))
    other = ctx.logs.find(level='warning')
    self.assertFalse(other is None)
    self.assertEqual(len(other) == 2)


The *exists* and *finds* api's will find logs that match the supplied keyword
arguments, using the key to look up the attribute on the logging.LogRecord
instances instances. Matching for strings is partial, i.e. *needle in
haystack*, not just *needle == haystack*.


