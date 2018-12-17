import textwrap

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import ViewList
from sphinx.util.nodes import nested_parse_with_titles

from talisker.config import CONFIG_META


class talisker_config(nodes.Structural, nodes.Element):
    pass


def visit_config_node(self, node):
    pass


def depart_config_node(self, node):
    pass


def extract_docstring(docstring):
    first_line, _, rest = docstring.partition('\n')
    dedented = [first_line.strip()]
    if rest:
        dedented.append(textwrap.dedent(rest))
    return '\n'.join(dedented)


class ConfigDirective(Directive):

    def run(self):
        config_nodes = []
        for name, (attr, doc) in CONFIG_META.items():
            # add title and link
            id = nodes.make_id('config-' + name)
            node = talisker_config()
            section = nodes.section(ids=[id])
            section += nodes.title(name, name)
            node += section

            # render docstring as ReST
            viewlist = ViewList()
            docstring = extract_docstring(doc)
            for i, line in enumerate(docstring.splitlines()):
                viewlist.append(line, 'config.py', i)
            doc_node = nodes.section()
            doc_node.document = self.state.document
            nested_parse_with_titles(self.state, viewlist, doc_node)
            node += doc_node

            config_nodes.append(node)

        return config_nodes


def setup(app):
    app.add_node(talisker_config, html=(visit_config_node, depart_config_node))
    app.add_directive('talisker_config', ConfigDirective)
