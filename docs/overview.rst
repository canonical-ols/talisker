.. highlight:: python

========
Overview
========


Goals
-----

Talisker is designed with the following high level goals:

 * to provide a standard platform for running wsgi apps
 * to support both operational and developer workflows in the same tool
 * to be easy as possible to integrate with any wsgi app and framework

The original motivation was to standardise tooling across a number of different
wsgi services, and improve the status quo along the way. Some of the
inspiration came from `Finagle <https://twitter.github.io/finagle/>`_,
Twitter's service framework for the JVM, particularly the operational
standardisation it provides.

In particular, we wanted to standardise how we monitor applications in
production, including logging, metrics, errors and alerts. Talisker provides
a single library to do this for all our apps, that our operations tooling can
configure easily, and means the application doesn't need to care about it.

Also we wanted to provide best practice features for applications to use. So we
added support for structured logging, integrated with the python stdlib
logging. This allows developers to add custom tags to their logs, as well as
add operational tags. We also provide easy to use helpers for best practice
usage of things like statsd clients and requests sessions, which were used
inconsistently across our projects, with repeated performance problems.


FAQ
---

Some questions that have actually been asked, if not particularly
frequently.

1. Why does talisker use a custom entry point? Wouldn't it be better to just be
   some WSGI middleware?

   There are 3 reasons for using a talisker specific entry point

   1. to configure stdlib logging early, *before* any loggers are created

   2. to allow for easy configuration of gunicorn for logging, statsd and
      other things.

   3. to do things like automatically wrap your wsgi in app in some simple
      standard middleware, to provide request id tracing and other things.

   If it was just middleware, logging would get configured too late for
   gunicorn's logs to be affected, and you would need to add explicit middleware
   and config to your app and its gunicorn config. Doing it as an alternate
   entry point means you literally just switch out gunicorn for talisker, and
   you are good to go.


2. Why just gunicorn? Why not twistd, or waitress, etc?

   Simply because we use gunicorn currently. Integrating with other wsgi
   application runners is totally possible, twistd support is in the works,
   with uwsgi support on the road map.


3. Why is it called talisker?

   'WSGI' sort of sounds like 'whisky' if you say it quick. One of my favourite
   whiskies is Talisker, I've even visited the distillery on the Isle of Skye.
   Also, Talisker is a heavily peated malt whisky, which is not to everyone's taste,
   which seemed to fit thematically with a WSGI runtime that is also very
   opinionated and probably not to everyone's taste.  Also, it has 8 characters
   just like gunicorn, and it wasn't taken on PyPI.
