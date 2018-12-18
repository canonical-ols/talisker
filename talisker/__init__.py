#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa
import logging
import sys
import textwrap
import os

from future.utils import exec_
# be *very* careful about what is imported here, as any stdlib loggers that are
# created can not be changed!
from talisker.config import get_config
from talisker.util import ensure_extra_versions_supported, pkg_is_installed
from talisker.context import CONTEXT, clear as clear_context  # noqa

__version__ = '0.11.0'
__all__ = [
    'initialise',
    'get_config',
    'run',
    'run_gunicorn',
    'run_celery',
    'run_gunicorn_eventlet',
    'run_gunicorn_gevent',
]
_early_log_messages = []
prometheus_multiproc_cleanup = False


def _log(name, level, *args, **kwargs):
    """Deferred log wrapper"""
    logger = logging.getLogger(name)
    getattr(logger, level)(*args, **kwargs)


def early_log(name, level, *args, **kwargs):
    """Logger wrap for talisker startup code.

    Collects logs for later processing when logging is initialised
    """
    _early_log_messages.append((name, level, args, kwargs))


def _flush_early_logs():
    global early_log
    # process pending logs
    for name, level, args, kwargs in _early_log_messages:
        _log(name, level, *args, **kwargs)
    _early_log_messages[:] = []

    # switch to immediate logging for any further early logs
    early_log = _log


def initialise(env=os.environ):
    global early_log

    config = get_config(env)
    import talisker.logs
    talisker.logs.configure(config)
    _flush_early_logs()

    # now that logging is set up, initialise other modules
    # sentry first, so we can report any further errors in initialisation
    # TODO: add deferred logging, so we can set up sentry first thing
    import talisker.sentry
    talisker.sentry.get_client()
    import talisker.statsd
    talisker.statsd.get_client()
    clear_contexts()
    return config


def clear_contexts():
    """Helper to clear any thread local contexts."""
    import talisker.sentry
    clear_context()
    client = talisker.sentry.get_client()
    client.context.clear()
    client.transaction.clear()


class RunException(Exception):
    pass


def run():
    """Initialise Talisker then exec python script."""
    initialise()
    logger = logging.getLogger('talisker.run')

    name = sys.argv[0]
    if '__main__.py' in name:
        # friendlier message
        name = '{} -m talisker'.format(sys.executable)

    extra = {}
    try:
        if len(sys.argv) < 2:
            raise RunException('usage: {} <script>  ...'.format(name))

        script = sys.argv[1]
        extra['script'] = script
        with open(script, 'rb') as f:
            code = compile(f.read(), script, 'exec')

        # pretend we just invoked python script.py by mimicing usual python
        # behavior
        sys.path.insert(0, os.path.dirname(script))
        sys.argv = sys.argv[1:]
        globs = {}
        globs['__file__'] = script
        globs['__name__'] = '__main__'
        globs['__package__'] = None

        clear_contexts()
        exec_(code, globs, None)

    except Exception:
        logger.exception('Unhandled exception', extra=extra)
        sys.exit(1)


def format_docstring(docstring, width):
    short, _, long = docstring.partition('\n\n')
    short = textwrap.wrap(' '.join(short.split()), width)
    if long:
        long = textwrap.wrap(' '.join(long.split()), width)
    return short, long


def run_help():
    """
    Usage: talisker.help [CONFIG NAME]

    Talisker provides some executable wrappers, which initialise Talisker
    and then simply pass through any supplied arguments to underlying command.

     - talisker.gunicorn wraps the regular gunicorn invocation
     - talisker.celery wraps the celery command
     - talisker.run wraps a regular call to python, and takes a script to run

    Talisker can be configured by the environment variables listed below. These
    variable can also be supplied in a python file, although environment
    variables override any file configuration.
    """
    width = 80
    indent = 30
    rest = width - indent
    indent_str = '\n' + ' ' * indent
    metadata = get_config().metadata()

    if len(sys.argv) > 1:
        name = sys.argv[1]
        if name.upper() not in metadata:
            sys.stderr.write('Invalid config: {}\n'.format(name))
            sys.exit('Invalid config: {}'.format(name))

        doc = metadata[name].doc
        if doc is None:
            short = 'No documentation'
            long = []
        else:
            short, long = format_docstring(doc, width)

        print(name)
        print()
        print('\n'.join(short))
        print()
        if long:
            print('\n'.join(long))
            print()

    else:
        # print header
        print(textwrap.dedent(run_help.__doc__).lstrip())
        print()

        for name, meta in metadata.items():
            if meta.doc is not None:
                short, long = format_docstring(meta.doc, rest)
                print('{:{indent}}{}'.format(
                    name, indent_str.join(short), indent=indent)
                )


def run_celery(argv=sys.argv):
    initialise()
    os.environ['CELERYD_REDIRECT_STDOUTS'] = 'False'
    # technically we don't need this, as we disable celery's logging
    # altogether, but it doesn't hurt
    os.environ['CELERYD_HIJACK_ROOT_LOGGER'] = 'False'
    ensure_extra_versions_supported('celery')
    import talisker.celery
    from celery.bin.celery import main
    talisker.celery.enable_signals()
    clear_contexts()
    main(argv)


def run_gunicorn():
    config = get_config()

    # configure prometheus_client early as possible
    if pkg_is_installed('prometheus-client'):
        # Early throw-away parsing of gunicorn config, as we need to decide
        # whether to enable prometheus multiprocess before we start importing
        from gunicorn.app.wsgiapp import WSGIApplication
        g_cfg = WSGIApplication().cfg
        if g_cfg.workers > 1 or 'prometheus_multiproc_dir' in os.environ:
            from talisker.prometheus import setup_prometheus_multiproc
            async_workers = ('gevent', 'eventlet')
            # must be done before prometheus_client is imported *anywhere*
            setup_prometheus_multiproc(
                any(n in g_cfg.worker_class_str for n in async_workers)
            )

    initialise()

    import talisker.gunicorn

    if pkg_is_installed('celery'):
        import talisker.celery
        talisker.celery.enable_signals()

    app = talisker.gunicorn.TaliskerApplication(
        "%(prog)s [OPTIONS] [APP_MODULE]", config.devel, config.debuglog)
    clear_contexts()
    return app.run()


# these two entrypoints workaround a bug in requests on python 3.6 for tls
# https://github.com/requests/requests/issues/3752
# they may go away once requests fixes this issue
def run_gunicorn_eventlet():
    # this is taken from gunicorn EventletWorker.patch()
    import eventlet
    eventlet.monkey_patch(os=False)
    run_gunicorn()


def run_gunicorn_gevent():
    import gevent
    # this is taken from gunicorn GeventWorker.patch()
    from gevent import monkey
    if gevent.version_info[0] == 0:
        monkey.patch_all()
    else:
        monkey.patch_all(subprocess=True)
    run_gunicorn()
