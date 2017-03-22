from __future__ import print_function
import os
import argparse

from setuptools.config import read_configuration
from pip.req.req_file import parse_requirements
from pip.req.req_install import InstallRequirement
from pip.download import PipSession


def get_source(comes_from):
    index = comes_from.find(' (line ')
    if index != -1:
        comes_from = comes_from[:index]
    if comes_from.startswith('-r '):
        comes_from = comes_from[3:]
    return comes_from


def print_file(filename, requirements):
    file = None
    for requirement in requirements:
        if not requirement.match_markers():
            continue

        comes_from = get_source(requirement.comes_from)
        if comes_from != file:
            if file is not None:
                print()
            print('# ' + comes_from)
            file = comes_from

        found = False
        specs = [(r.version, r) for r in requirement.specifier]
        if specs:
            version, spec = min(specs)
            if version in spec:
                found = True
                print('{}=={}'.format(requirement.name, version))
            else:
                print('# no explicit minimum')
        if not found:
            print(str(requirement.req))
    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements", nargs="*")
    parser.add_argument("--extras", default="")

    args = parser.parse_args()
    session = PipSession()
    options = {}

    if os.path.exists('setup.cfg'):
        options = read_configuration('setup.cfg').get('options', {})

    install_requires = options.get('install_requires', [])
    extras_require = options.get('extras_require', {})

    if install_requires:
        fname = 'setup.cfg:options.install_requires'
        print_file(
            fname,
            (InstallRequirement.from_line(l, fname) for l in install_requires),
        )

    for extra, requires in extras_require.items():
        if extra in args.extras:
            fname = 'setup.cfg:options.extras_require:' + extra
            print_file(
                fname,
                (InstallRequirement.from_line(l, fname) for l in requires),
            )

    for filename in args.requirements:
        print_file(filename, parse_requirements(filename, session=session))
