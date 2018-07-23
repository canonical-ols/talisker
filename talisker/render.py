#
# Copyright (c) 2015-2018 Canonical, Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from builtins import *  # noqa

import collections
import html
from itertools import chain

__all__ = [
    'render',
    'Content',
    'Head',
    'Link',
    'Table',
]

RENDERERS = {
    'text/html': lambda x: x.html(),
    'text/plain': lambda x: x.text(),
}


def render(type, head, content):
    """Render some Content."""
    renderer = RENDERERS[type]
    yield renderer(head)
    for block in content:
        yield renderer(block)


class Content(object):
    """Default simple content object, which can render as text or html."""
    def __init__(
            self, content, tag=None, attrs=None,
            html=True, text=True, escape=True):
        self.content = content
        self.tag = tag
        self.attrs = attrs if attrs is not None else {}
        self.render_html = html
        self.render_text = text
        self.escape = escape

    def html(self):
        if not self.render_html:
            return ''
        return self.html_content()

    def text(self):
        if not self.render_text:
            return ''
        return self.text_content()

    def html_content(self):
        content = self.content
        if self.escape:
            content = html.escape(self.content)
        if self.tag is None:
            return content

        attrs = [
            '{}="{}"'.format(html.escape(k), html.escape(v, quote=True))
            for k, v in self.attrs.items()
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
        }
        super().__init__(self.link_text, tag='a', attrs=attrs, **super_kwargs)

    def text_content(self):
        if self.host and '://' not in self.href:
            # relative url, not much use in text, so look for host
            return self.host.rstrip('/') + '/' + self.href.lstrip('/')
        else:
            return self.href


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
                output.append('{:{w}}'.format(col, w=w))
            yield ''.join(output)


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
