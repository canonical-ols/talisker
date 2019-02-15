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

import collections
import html
import json
from itertools import chain

import werkzeug

__all__ = [
    'render_best_content_type',
    'Content',
    'Head',
    'Link',
    'Table',
    'PreformattedText',
]


RENDERERS = {
    'text/html': lambda x: x.html(),
    'text/plain': lambda x: x.text(),
    'application/json': lambda x: x._json(),
}


class StringEncoder(json.JSONEncoder):
    def default(self, o):
        return str(o)


def render_best_content_type(environ, title, content):
    """Return a response rendered using talisker.render."""
    request = werkzeug.Request(environ)
    content_type = request.accept_mimetypes.best_match(
        ['text/plain', 'text/html', 'application/json'],
        default='text/plain',
    )
    return (
        content_type,
        render_type(content_type, Head(title), content),
    )


def render_type(type, head, content):
    """Render some Content."""

    renderer = RENDERERS[type]
    parts = [renderer(head)]
    parts.extend(renderer(block) for block in content)

    if type == 'application/json':
        output = collections.OrderedDict()
        output.update(p for p in parts if p is not None)
        output = json.dumps(output, cls=StringEncoder)
    else:
        output = '\n'.join(parts)

    return output.encode('utf8')


class Content(object):
    """Default simple content object, which can render as text or html."""
    def __init__(
            self, content, tag=None, id=None, attrs=None,
            html=True, text=True, json=True, escape=True):
        self.content = content
        self.tag = tag
        self.id = id
        self.attrs = attrs if attrs is not None else {}
        if id and 'id' not in self.attrs:
            self.attrs['id'] = id
        self.render_html = html
        self.render_text = text
        self.render_json = json
        self.escape = escape

    def html(self):
        if not self.render_html:
            return ''
        return self.html_content()

    def text(self):
        if not self.render_text:
            return ''
        return self.text_content()

    def _json(self):
        if self.render_json and self.id:
            return self.id, self.json_content()

    def html_content(self):
        content = self.content
        if self.escape:
            content = html.escape(self.content)
        if self.tag is None:
            return content

        attrs = None
        if self.attrs:
            attrs = [
                '{}="{}"'.format(html.escape(k), html.escape(v, quote=True))
                for k, v in sorted(self.attrs.items())
            ]
        return '<{tag}{attrs}>{content}</{tag}>'.format(
            tag=self.tag,
            attrs=(" " + " ".join(attrs)) if attrs else '',
            content=content,
        )

    def text_content(self):
        output = [self.content]
        if self.tag in 'h1 h2 h3 h4 h5 h6':
            output.append('=' * len(output[0]))
        output.append('\n')
        return '\n'.join(output)

    def json_content(self):
        return self.content


class Link(Content):
    """A hyperlink."""
    def __init__(self, text, href, *args, **kwargs):
        self.link_text = text.format(*args, **kwargs)

        self.href = href.format(*args, **kwargs)
        self.host = kwargs.get('host', None)
        attrs = kwargs.get('attrs', {})
        attrs['href'] = self.href

        super_kwargs = {
            'text': kwargs.get('text', True),
            'html': kwargs.get('html', True),
            'id': kwargs.get('id'),
        }
        super().__init__(
            self.link_text, tag='a', attrs=attrs, **super_kwargs
        )

    def text_content(self):
        if self.host and '://' not in self.href:
            # relative url, not much use in text, so look for host
            return self.host.rstrip('/') + '/' + self.href.lstrip('/')
        else:
            return self.href

    def json_content(self):
        return {
            'text': self.link_text,
            'href': self.href,
        }


class Table(Content):
    def __init__(self, *args, **kwargs):
        self.headers = kwargs.pop('headers', None)
        super().__init__(*args, **kwargs)

    def html_content(self):
        output = ['<table>']
        if self.headers is not None:
            output.append('<thead>')
            output.append('<tr>')
            for header in self.headers:
                if isinstance(header, Content):
                    h = header.html()
                else:
                    h = html.escape(str(header))
                output.append('<th>{}</th>'.format(h))
            output.append('</tr>')
            output.append('</thead>')
        output.append('<tbody>')
        for row in self.content:
            output.append('<tr>')
            for col in row:
                if isinstance(col, Content):
                    c = col.html()
                else:
                    c = html.escape(str(col))
                output.append('<td>{}</td>'.format(c))
            output.append('</tr>')
        output.append('</tbody>')
        output.append('</table>')
        return '\n'.join(output)

    def text_content(self):
        headers = []
        table = []
        widths = collections.defaultdict(int)
        if self.headers is not None:
            for i, header in enumerate(self.headers):
                if isinstance(header, Content):
                    headers.append(header.text())
                else:
                    headers.append(str(header))
                widths[i] = max(widths[i], len(headers[-1]))

        for row in self.content:
            columns = []
            for i, column in enumerate(row):
                if isinstance(column, Content):
                    columns.append(column.text())
                else:
                    columns.append(str(column))
                widths[i] = max(widths[i], len(columns[-1]))
            table.append(columns)

        border = ['-' * (sum(w + 2 for w in widths.values()) - 2)]
        rows = []
        if self.headers:
            rows.append(self.format_table([headers], widths))

        rows.extend([
            border,
            self.format_table(table, widths),
            border,
            ['\n'],
        ])

        return '\n'.join(chain(*rows))

    def format_table(self, table, widths):
        for row in table:
            output = []
            for i, col in enumerate(row):
                w = widths[i]
                if i < len(row) - 1:
                    w += 2
                output.append('{:<{w}}'.format(col, w=w))
            yield ''.join(output)

    def json_content(self):
        if not self.content:
            return {}
        elif len(self.content[0]) == 2:
            # definition table
            return collections.OrderedDict(self.content)

        content = []
        # multi-value table
        for row in self.content:
            row_data = (
                r.json_content() if isinstance(r, Content) else r for r in row
            )
            if self.headers:
                content.append(
                    collections.OrderedDict(zip(self.headers, row_data))
                )
            else:
                content.append(row_data)
        return content


class Head(Content):
    CDN = '//cdnjs.cloudflare.com/ajax/libs'
    HTML_HEADER = """
    <head>
        <title>Talisker: {title}</title>
        <link rel="stylesheet" href="{cdn}/normalize/8.0.0/normalize.min.css">
        <link rel="stylesheet" href="{cdn}/milligram/1.3.0/milligram.min.css">
        <style>body {{{{ margin: 1em }}}}</style>
    </head>
    """.format(cdn=CDN, title='{title}')

    def __init__(self, title):
        super().__init__(title)
        self.title = title

    def html_content(self):
        return self.HTML_HEADER.format(title=self.title)

    def text_content(self):
        title = 'Talisker: {}'.format(self.title)
        border = '=' * len(title)
        return '\n'.join(['', border, title, border, '\n'])

    def json_content(self):
        return self.title


class PreformattedText(Content):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('tag', 'pre')
        super().__init__(*args, **kwargs)

    def text_content(self):
        return self.content

    def json_content(self):
        return self.content.split('\n')
