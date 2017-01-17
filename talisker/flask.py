# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import logging

import flask
import raven.contrib.flask
from raven.utils.conf import convert_options

import talisker.sentry


__all__ = [
    'sentry',
    'register',
    'TaliskerApp',
]


def _get_flask_sentry_config(app):
    # frustratingly, raven's flask support embeds this default config in the
    # middle of a function, so there is no easy way to access it.
    # To avoid having to subclass the client, we copy the defaults here
    # TODO: upstream a change to raven that allows us to reuse the flask
    # defaults it provides

    includes = (set(app.config.get('SENTRY_INCLUDE_PATHS', [])) |
                set([app.import_name]))
    options = convert_options(
        app.config, {
            'include_paths': includes,
            # support legacy RAVEN_IGNORE_EXCEPTIONS
            'ignore_exceptions': [
                '{0}.{1}'.format(x.__module__, x.__name__)
                for x in app.config.get('RAVEN_IGNORE_EXCEPTIONS', [])
            ],
        }
    )
    # Note: we differ from upstream here, as there 'extra': app config is
    # ignored in current sentry. We add it as a tag instead.
    if options.get('tags') is None:
        options['tags'] = {}
    options['tags']['flask_app'] = app.name
    return options


def _set_flask_sentry_client(app, **kwargs):
    config = _get_flask_sentry_config(app)
    config.update(kwargs)
    # update the sentry client with the app config
    logging.getLogger(__name__).info(
        "updating sentry config with flask app configuration")
    talisker.sentry.set_client(**config)


def sentry(app, dsn=None, transport=None, **kwargs):
    """Enable sentry for a flask app, talisker style."""
    # transport is just to support testing, not used in prod
    _set_flask_sentry_client(app, dsn=dsn, transport=transport)
    kwargs['logging'] = False
    kwargs['client'] = talisker.sentry.get_client()
    kwargs['wrap_wsgi'] = False
    return raven.contrib.flask.Sentry(app, **kwargs)


def _setup(app):
    # silence flasks handlers log handlers.
    app.config['LOGGER_HANDLER_POLICY'] = 'never'
    sentry(app)


def register(app):
    """Register a flask app with talisker."""
    _setup(app)
    # hack to actually remove flasks handlers
    app._logger = logging.getLogger(app.logger_name)


class TaliskerApp(flask.Flask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _setup(self)

    # flasks default logger is not needed with talisker
    @property
    def logger(self):
        return logging.getLogger(self.logger_name)
