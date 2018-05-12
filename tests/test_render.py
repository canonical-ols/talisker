# Copyright (C) 2016- Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

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
