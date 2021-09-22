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

import textwrap

from talisker.render import (
    Content,
    Link,
    Table,
    PreformattedText,
)


def test_content_simple_string():
    content = Content('test', tag='p', id='id', attrs={'foo': 'foo'})
    assert content.html() == '<p foo="foo" id="id">test</p>'
    assert content.text() == 'test\n\n'
    assert content._json() == ('id', 'test')
    assert Content('test', tag='h1').text() == 'test\n====\n\n'
    assert Content('test')._json() is None


def test_content_escaped():
    content = Content('te<br>st', tag='p', id='id<br>')
    assert content.html() == '<p id="id&lt;br&gt;">te&lt;br&gt;st</p>'
    assert content.text() == 'te<br>st\n\n'
    assert content._json() == ('id<br>', 'te<br>st')


def test_content_not_escaped():
    content = Content(
        '<a>test</a>', tag='p', id='id<br>', escape=False)
    assert content.html() == '<p id="id&lt;br&gt;"><a>test</a></p>'
    assert content.text() == '<a>test</a>\n\n'
    assert content._json() == ('id<br>', '<a>test</a>')


def test_content_disabled():
    assert Content('test', html=False).html() == ''
    assert Content('test', text=False).text() == ''
    assert Content('test', json=False)._json() is None


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
    assert Link('link', '/link', id='link')._json() == (
        'link', {'href': '/link', 'text': 'link'}
    )


def test_table():
    rows = [
        ['a', 'b', 'c'],
        ['d', 'e', Link('foo', '/foo')],
    ]
    table = Table(rows, headers=['1', '2', '3'], id='table')

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

    id, obj = table._json()
    assert id == 'table'
    assert obj == [
        {'1': 'a', '2': 'b', '3': 'c'},
        {'1': 'd', '2': 'e', '3': {'href': '/foo', 'text': 'foo'}},
    ]

    # special case in json for 2 column tables
    table2 = Table(list(dict(a=1, b=2).items()), id='table')
    assert table2._json() == ('table', {'a': 1, 'b': 2})


def test_preformatted():
    text = textwrap.dedent("""
        This is
          a preformatted
            multiline text fragment.
    """).strip()
    pre = PreformattedText(text, id='text')

    pre.text() == text
    pre.html() == '<pre id="text">' + text + '<pre>'
    pre._json() == ('text', text.split('\n'))
