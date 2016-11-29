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

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import raven
from raven.contrib.flask import Sentry
from raven.utils.conf import convert_options

import talisker.raven
from talisker.util import module_cache


def get_flask_sentry_config(app, dsn=None):
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


@module_cache
def get_flask_sentry_client(app, **kwargs):
    # Flask uses its own client, as it's configured slightly differently from
    # the wsgi client
    config = get_flask_sentry_config(app)
    config.update(kwargs)
    talisker.raven.ensure_talisker_config(config)
    return raven.Client(**config)


def sentry(app, dsn=None, client=None):
    if client is None:
        client = get_flask_sentry_client(app, dsn=dsn)
    # logging and wsgi are already sorted by talisker
    return Sentry(app,
                  dsn=dsn,
                  client=client,
                  logging=False,
                  wrap_wsgi=False)
