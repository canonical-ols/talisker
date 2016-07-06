def revision():
    import revision
    return revision.__revision__


def version():
    import version
    return version.__version__


def bzr_version_info():
    from versioninfo import version_info
    return version_info['revno']


# TODO git_hash

revision_funcs = [
    revision,
    version,
    bzr_version_info,
]


def load_revision():
    for func in revision_funcs:
        try:
            return func()
        except:
            pass
        return 'unknown'


revision = load_revision()
http_safe_revision = revision.strip().replace('\n', '\\n')


def get():
    return revision


def header():
    return http_safe_revision
