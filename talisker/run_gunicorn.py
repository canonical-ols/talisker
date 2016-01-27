#!/home/wavy/.virtualenvs/talisker/bin/python
# -*- coding: utf-8 -*-
import sys

from gunicorn.app.wsgiapp import run

if __name__ == '__main__':
    sys.exit(run())
