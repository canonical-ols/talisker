from __future__ import absolute_import, division, print_function

from werkzeug.local import Local, LocalManager

context = Local()

# used in wsgi stack for clean up
manager = LocalManager(context)


def set_context(**kwargs):
    for k, v in kwargs.items():
        setattr(context, k, v)
