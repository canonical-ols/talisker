from subprocess import check_output as run
import sys
import tempfile

from talisker import revision
import pytest


def test_git(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    run(['git', 'init', '.'])
    run(['touch', 'foo'])
    run(['git', 'add', 'foo'])
    run(['git', 'commit', '-m', 'init'])
    rev = revision.git()
    assert len(rev.strip()) == 40


def set_up_bzr():
    run(['bzr', 'init', '.'])
    run(['touch', 'foo'])
    run(['bzr', 'add', 'foo'])
    run(['bzr', 'commit', '-m', 'init'])


def test_bzr(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    set_up_bzr()
    rev = revision.bzr()
    assert rev.strip() == b'1'


@pytest.mark.skipif(sys.version_info >= (3, 0), reason="requires python2")
def test_bzr_version_info_py2(monkeypatch):
    dir = tempfile.mkdtemp()
    monkeypatch.chdir(dir)
    monkeypatch.syspath_prepend(dir)
    set_up_bzr()
    vinfo = run(['bzr', 'version-info', '--format=python'])
    with open('versioninfo.py', 'wb') as f:
        f.write(vinfo)
    rev = revision.bzr_version_info()
    assert rev.strip() == '1'
