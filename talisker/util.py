from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from urllib.parse import urlparse


def parse_url(url, proto='http'):
    # urlparse won't parse properly without a protocol
    if not url.startswith(proto + '://'):
        url = proto + '://' + url
    return urlparse(url)
