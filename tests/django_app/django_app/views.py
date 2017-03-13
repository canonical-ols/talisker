import logging
from django.shortcuts import render
from django.http import HttpResponse

from django_app.celery import debug_task

from django.db import connection
from django.contrib.auth.models import User, Group


def error(request):
    User.objects.count()
    Group.objects.count()

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
