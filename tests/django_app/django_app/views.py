import logging
from django.shortcuts import render
from django.http import HttpResponse

from django_app.celery import debug_task

from django.contrib.auth.models import User


# Create your views here.
def error(request):
    raise Exception('test')


def db(request):
    count = User.objects.count()
    raise Exception('test')
    return HttpResponse('There are %d users' % count, status=200)


def celery(request):
    logging.getLogger(__name__).info('starting task')
    debug_task.delay()
    return HttpResponse('ok', status=200)
