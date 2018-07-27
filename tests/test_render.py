#
# Copyright (c) 2015-2018 Canonical, Ltd.
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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import textwrap

from talisker.render import (
    Content,
    Link,
    Table,
)


def test_content_simple_string():
    content = Content('test', tag='p', attrs={'id': 'id'})
    assert content.html() == '<p id="id">test</p>'
    assert content.text() == 'test\n\n'
    assert Content('test', tag='h1').text() == 'test\n====\n\n'


def test_content_escaped():
    content = Content('te<br>st', tag='p', attrs={'id': 'id<br>'})
    assert content.html() == '<p id="id&lt;br&gt;">te&lt;br&gt;st</p>'
    assert content.text() == 'te<br>st\n\n'


def test_content_not_escaped():
    content = Content(
        '<a>test</a>', tag='p', attrs={'id': 'id<br>'}, escape=False)
    assert content.html() == '<p id="id&lt;br&gt;"><a>test</a></p>'
    assert content.text() == '<a>test</a>\n\n'


def test_content_disabled():
    assert Content('test', html=False).html() == ''
    assert Content('test', text=False).text() == ''


def test_link():
    assert Link('link', '/link').html() == '<a href="/link">link</a>'
    assert Link('{}', '/link/{}', 'x').html() == '<a href="/link/x">x</a>'
    assert Link('{foo}', '/link/{foo}', foo='bar').html() == (
        '<a href="/link/bar">bar</a>'
    )
    assert Link('link', '/link').text() == '/link'
    assert Link('link', '/link', host='http://example.com').text() == (
        'http://example.com/link'
    )


def test_table():
    rows = [
        ['a', 'b', 'c'],
        ['d', 'e', Link('foo', '/foo')],
    ]
    table = Table(rows, headers=['1', '2', '3'])

    assert table.html() == textwrap.dedent("""
        <table>
        <thead>
        <tr>
        <th>1</th>
        <th>2</th>
        <th>3</th>
        </tr>
        </thead>
        <tbody>
        <tr>
        <td>a</td>
        <td>b</td>
        <td>c</td>
        </tr>
        <tr>
        <td>d</td>
        <td>e</td>
        <td><a href="/foo">foo</a></td>
        </tr>
        </tbody>
        </table>
    """).strip()

    # Add # characters to stop editors striping eol whitespace!
    assert table.text() == textwrap.dedent("""
        1  2  3   #
        ----------#
        a  b  c   #
        d  e  /foo#
        ----------#

    """).replace('#', '').lstrip()
