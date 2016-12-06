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

import raven.contrib.flask
from raven.utils.conf import convert_options

import talisker.raven


def get_flask_sentry_config(app):
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


def set_flask_sentry_client(app, **kwargs):
    config = get_flask_sentry_config(app)
    config.update(kwargs)
    # update the sentry client with the app config
    logging.getLogger(__name__).info(
        "updating sentry config with flask app configuration")
    talisker.raven.set_client(**config)


def sentry(app, client_config=None):
    if client_config is None:
        client_config = {}
    set_flask_sentry_client(app, **client_config)
    client = talisker.raven.get_client()
    return raven.contrib.flask.Sentry(
            app, client=client, logging=False, wrap_wsgi=False)
