from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from werkzeug.local import Local, LocalManager

context = Local()

# used in wsgi stack for clean up
manager = LocalManager(context)


def set_context(**kwargs):
    for k, v in list(kwargs.items()):
        setattr(context, k, v)
