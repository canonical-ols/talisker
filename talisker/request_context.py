from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from werkzeug.local import Local, LocalManager

# a per request context. Generally, this will be the equivelant of thread local
# storage, but if greenlets are being used, it will be a greenlet local.
request_context = Local()

# used in wsgi stack for clean up
_manager = LocalManager(request_context)
cleanup = _manager.make_middleware


def set_request_context(**kwargs):
    for k, v in list(kwargs.items()):
        setattr(request_context, k, v)
