##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##
import logging
from django.shortcuts import render
from django.http import HttpResponse

from django_app.celery import debug_task

from django.db import connection
from django.contrib.auth.models import User, Group


def index(request):
    return HttpResponse('ok', status=200)


def error(request):
    User.objects.count()
    Group.objects.count()
    User.objects.get(pk=1)

    with connection.cursor() as cursor:
        cursor.execute("select add(2, 3);")
        cursor.fetchone()
        cursor.execute("select add(%s, %s)", [2, 3])
        cursor.fetchone()
        cursor.callproc('add', [2, 3])
        cursor.fetchone()

    raise Exception('test')


def db(request):
    count = User.objects.count()
    raise Exception('test')
    return HttpResponse('There are %d users' % count, status=200)


def celery(request):
    logging.getLogger(__name__).info('starting task')
    debug_task.delay()
    return HttpResponse('ok', status=200)
