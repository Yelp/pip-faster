# NOTE WELL: No side-effects are allowed in __init__ files. This means you!
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import os
from re import compile as Regex
from re import DOTALL
from re import MULTILINE

from pip._internal.wheel import Wheel
from py._path.local import LocalPath as Path

TOP = Path(__file__) / '../../..'
COVERAGE_REQS = TOP.join('requirements.d/coverage.txt')


def requirements(reqs, path='requirements.txt'):
    """Write a requirements.txt file to the current working directory."""
    Path(path).write(reqs)


def run(*cmd, **env):
    if env:
        from os import environ
        tmp = env
        env = environ.copy()
        env.update(tmp)
    else:
        env = None

    from .capture_subprocess import capture_subprocess
    from venv_update import info, colorize
    info('\nTEST> ' + colorize(cmd))
    out, err = capture_subprocess(cmd, env=env)
    err = strip_coverage_warnings(err)
    return out, err


def venv_update(*args, **env):
    # we get coverage for free via the (patched) pytest-cov plugin
    return run('venv-update', *args, **env)


def venv_update_symlink_pwd():
    # I wish I didn't need this =/
    # surely there's a better way -.-
    # NOTE: `pip install TOP` causes an infinite copyfiles loop, under tox >.<
    from venv_update import __file__ as venv_update_path, dotpy

    # symlink so that we get coverage, where possible
    venv_update_path = Path(dotpy(venv_update_path))
    local_vu = Path(venv_update_path.basename)
    local_vu.mksymlinkto(venv_update_path)


# coverage.py adds some helpful warnings to stderr, with no way to quiet them.
coverage_warnings_regex = Regex(
    r'^Coverage.py warning: (%s)\n' % '|'.join((
        r'Module .* was never imported\.',
        r'No data was collected\.',
        r'Module venv_update was previously imported, but not measured\.',
    )),
    flags=MULTILINE,
)


def strip_coverage_warnings(stderr):
    return coverage_warnings_regex.sub('', stderr)


# pip adds some helpful warnings to stderr, with no way to quiet them.
pip_warnings_regex = Regex(
    '|'.join((
        r"^  Url '[^']*/\.cache/pip-faster/wheelhouse' is ignored: it is neither a file nor a directory\.\n",
        r'^You are using pip version [0-9.]+, however version [0-9.]+ is available\.\n',
        r"^You should consider upgrading via the 'pip install --upgrade pip' command\.\n",
        r"^DEPRECATION: Python 2\.7 will reach the end of its life on January 1st, 2020\. Please upgrade your Python as Python 2\.7 won't be maintained after that date\. A future version of pip will drop support for Python 2\.7\.\n",  # noqa: E501
        r"^DEPRECATION: Python 2\.7 will reach the end of its life on January 1st, 2020\. Please upgrade your Python as Python 2\.7 won't be maintained after that date\. A future version of pip will drop support for Python 2\.7\. More details about Python 2 support in pip, can be found at https://pip\.pypa\.io/en/latest/development/release-process/#python-2-support\n",  # noqa: E501
        r"DEPRECATION: Python 2\.7 reached the end of its life on January 1st, 2020\. Please upgrade your Python as Python 2\.7 is no longer maintained\. pip 21\.0 will drop support for Python 2\.7 in January 2021\. More details about Python 2 support in pip can be found at https://pip\.pypa\.io/en/latest/development/release-process/#python-2-support pip 21\.0 will remove support for this functionality\.",  #noqa: E501
        r"^DEPRECATION: Python 3\.4 support has been deprecated. pip 19\.1 will be the last one supporting it\. Please upgrade your Python as Python 3\.4 won't be maintained after March 2019 \(cf PEP 429\)\.\n",   # noqa: E501
        r'^DEPRECATION: A future version of pip will drop support for Python 2\.7\.\n',  # noqa: E501
        r'^DEPRECATION: A future version of pip will drop support for Python 2\.7\. More details about Python 2 support in pip, can be found at https://pip\.pypa\.io/en/latest/development/release-process/#python-2-support\n',  # noqa: E501
        r'\S+ UserWarning: Setuptools will stop working on Python 2.*warnings.warn.*$',  # noqa: E501
    )),
    flags=MULTILINE | DOTALL,
)


def strip_pip_warnings(stderr):
    stderr = pip_warnings_regex.sub('', stderr)
    return stderr.strip()


def uncolor(text):
    # the colored_tty, uncolored_pipe tests cover this pretty well.
    from re import sub
    text = sub('\033\\[[^A-z]*[A-z]', '', text)
    text = sub('.\b', '', text)
    return sub('[^\n\r]*\r', '', text)


def pip_freeze(venv='venv'):
    from os.path import join
    out, err = run(join(venv, 'bin', 'pip'), 'freeze', '--local', '--all')

    # Most python distributions which have argparse in the stdlib fail to
    # expose it to setuptools as an installed package (it seems all but ubuntu
    # do this). This results in argparse sometimes being installed locally,
    # sometimes not, even for a specific version of python.
    # We normalize by never looking at argparse =/
    import re
    out = re.sub(r'argparse==[\d.]+\n', '', out, count=1)

    # We'll always have `pip`, `setuptools`, and `wheel` -- filter those out
    for pkg in ('pip', 'setuptools', 'wheel'):
        reg = re.compile(r'((?<=\n)|^){}==.*(\n|$)'.format(pkg))
        assert reg.search(out)
        out = reg.sub('', out)
    # The `coverage` version is floating
    out = re.sub('^coverage==.*', 'coverage==ANY', out, count=1)

    err = strip_pip_warnings(err)
    assert err == ''
    return out


def install_coverage(venv='venv'):
    venv = Path(venv)
    if not venv.exists():
        run('virtualenv', str(venv))
    run(str(venv.join('bin/python')), '-m', 'pip.__main__', 'install', '-r', str(COVERAGE_REQS))


def enable_coverage():
    from venv_update import Scratch
    install_coverage(Scratch().venv)


class OtherPython(object):
    """represents a python interpreter that doesn't match the "current" interpreter's version"""

    def __init__(self):
        import sys
        if sys.version_info[0] <= 2:
            self.interpreter = 'python3'
            self.version_prefix = '3.'
        else:
            self.interpreter = 'python2.7'
            self.version_prefix = '2.7.'


def cached_wheels(tmpdir):
    for _, _, filenames in os.walk(
            tmpdir.join('home', '.cache', 'pip-faster', 'wheelhouse').strpath,
    ):
        for filename in filenames:
            assert filename.endswith('.whl'), filename
            yield Wheel(filename)
