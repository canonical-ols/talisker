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


revision = 'unknown'


for func in revision_funcs:
    try:
        revision = func()
    except:
        pass
    else:
        break


http_safe_revision = repr(revision.strip()).replace('\n', '')


def get():
    return revision


def revision_header():
    return http_safe_revision
