#!/usr/bin/env python
"""
Build a collection of packages, to be used as a pytest fixture.

This script is reentrant IFF the destinations are not shared.
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import os
from contextlib import contextmanager
from sys import executable as python


@contextmanager
def chdir(path):
    if os.getcwd() == str(path):
        yield
        return

    from sys import stdout
    stdout.write('cd %s\n' % path)
    with path.as_cwd():
        yield


def run(cmd):
    from sys import stdout
    from subprocess import check_call
    from pipes import quote
    cmd_string = ' '.join(quote(arg) for arg in cmd)
    stdout.write('%s\n' % (cmd_string))
    check_call(cmd)


def make_copy(setuppy, dst):
    pkg = setuppy.dirpath().basename
    copy = dst.join('src', pkg).ensure(dir=True)

    # egg-info is also not reentrant-safe: it briefly blanks SOURCES.txt
    with chdir(setuppy.dirpath()):
        run((python, 'setup.py', '--quiet', 'egg_info', '--egg-base', str(copy)))

    from glob import glob
    sources = copy.join('*/SOURCES.txt')
    sources, = glob(str(sources))
    sources = open(sources).read().splitlines()

    for source in sources:
        source = setuppy.dirpath().join(source, abs=1)
        dest = copy.join(source.relto(setuppy))
        dest.dirpath().ensure(dir=True)
        source.copy(dest)
    return copy


def sdist(setuppy, dst):
    copy = make_copy(setuppy, dst)
    with chdir(copy):
        run(
            (python, 'setup.py', '--quiet', 'sdist', '--dist-dir', str(dst)),
        )


def build_one(src, dst):
    setuppy = src.join('setup.py')
    if setuppy.exists():
        sdist(setuppy, dst)

        if src.join('wheelme').exists():
            copy = make_copy(setuppy, dst)
            wheel(copy, dst)

        return True


def build_all(sources, dst):
    for source in sources:
        if build_one(source, dst):
            continue
        for source in sorted(source.listdir()):
            build_one(source, dst)


def wheel(src, dst):
    build = dst.join('build')
    build.ensure_dir()
    run((
        python, '-m', 'pip',
        'wheel',
        '--quiet',
        '--build-dir', str(build),
        '--wheel-dir', str(dst),
        str(src)
    ))
    build.remove()  # pip1.5 wheel doesn't clean up its build =/


def download_sdist(source, destination):
    run((
        python, '-m', 'pip',
        'download',
        '--quiet',
        '--no-deps',
        '--no-binary', ':all:',
        '--build-dir', str(destination.join('build')),
        '--dest', str(destination),
        str(source),
    ))


def do_build(sources, destination):
    build_all(sources, destination)
    wheel('virtualenv>=20', destination)
    wheel('coverage-enable-subprocess', destination)
    download_sdist('coverage', destination)
    download_sdist('coverage-enable-subprocess', destination)


def random_string():
    """return a short suffix that shouldn't collide with any subsequent calls"""
    import os
    import base64

    return '.'.join((
        str(os.getpid()),
        base64.urlsafe_b64encode(os.urandom(3)).decode('US-ASCII'),
    ))


def flock(path, blocking=True):
    import os
    fd = os.open(path, os.O_CREAT)

    import fcntl
    flags = fcntl.LOCK_EX  # exclusive
    if not blocking:  # :pragma:nobranch:
        flags |= fcntl.LOCK_NB  # non-blocking

    try:
        fcntl.flock(fd, flags)
    except IOError as error:  # :pragma:nocover: not always hit
        if error.errno == 11:  # EAGAIN: lock held
            return None
        else:
            raise
    else:
        return fd


def make_sdists(sources, destination):
    destination.dirpath().ensure(dir=True)

    lock = destination.new(ext='lock')
    if flock(lock.strpath, blocking=False) is None:  # :pragma:nocover: not always hit
        print('lock held; waiting for other thread...')
        flock(lock.strpath, blocking=True)
        return

    staging = destination.new(ext=random_string())
    staging.ensure(dir=True)

    do_build(sources, staging)
    if destination.islink():  # :pragma:nocover:
        old = destination.readlink()
    else:
        old = None

    link = staging.new(ext='ln')
    link.mksymlinkto(staging, absolute=False)
    link.rename(destination)

    if old is not None:  # :pragma:nocover:
        destination.dirpath(old).remove()


def main():
    assert 'PIP_INDEX_URL' not in os.environ, os.environ['PIP_INDEX_URL']
    from sys import argv
    argv = argv[1:]
    sources, destination = argv[:-1], argv[-1]

    from py._path.local import LocalPath
    sources = tuple([LocalPath(src) for src in sources])
    destination = LocalPath(destination)

    return make_sdists(sources, destination)


if __name__ == '__main__':
    exit(main())
