import subprocess
import sys

revision = None
http_safe_revision = None


def _run(args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def git():
    return _run(['git', 'rev-parse', 'HEAD'])


def bzr():
    return _run(['bzr', 'revno'])


def hg():
    return _run(['hg', 'id', '-i'])


def bzr_version_info():
    from versioninfo import version_info
    return version_info['revno']


def setup_py():
    return subprocess.check_output([sys.executable, 'setup.py', '--version'])


revision_funcs = [
    git,
    bzr,
    bzr_version_info,
    hg,
    setup_py,
]


def load_revision():
    for func in revision_funcs:
        try:
            rev = func()
            if rev:
                return rev.strip().decode('utf8')
        except:
            pass
    return u'unknown'


def get():
    global revision
    if revision is None:
        revision = load_revision()
    return revision


def set(custom_revision):
    global revision, http_safe_revision
    revision = custom_revision
    http_safe_revision = None


def header():
    global http_safe_revision
    if http_safe_revision is None:
        http_safe_revision = get().strip().replace('\n', '\\n')
    return http_safe_revision
