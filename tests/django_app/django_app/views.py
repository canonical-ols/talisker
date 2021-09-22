#
# Copyright (c) 2015-2021 Canonical, Ltd.
# 
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
# 
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
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
