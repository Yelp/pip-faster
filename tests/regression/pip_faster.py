from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import sys

import pytest

from testing import cached_wheels
from testing import enable_coverage
from testing import install_coverage
from testing import Path
from testing import pip_freeze
from testing import run
from testing import strip_pip_warnings
from testing import uncolor
from venv_update import __version__


def make_venv():
    enable_coverage()
    venv = Path('venv')
    run('virtualenv', venv.strpath)
    install_coverage(venv.strpath)

    pip = venv.join('bin/pip').strpath
    run(pip, 'install', 'venv-update==' + __version__)
    return venv


@pytest.mark.usefixtures('pypi_server', 'tmpdir')
def test_circular_dependencies():
    """pip-faster should be able to install packages with circular
    dependencies."""
    venv = make_venv()

    out, err = run(
        venv.join('bin/pip-faster').strpath,
        'install',
        '-vv',  # show debug logging
        'circular-dep-a',
    )
    err = strip_pip_warnings(err)
    assert err.strip() == (
        'Circular dependency! circular-dep-a==1.0 '
        '(from circular-dep-b==1.0->circular-dep-a)'
    )
    out = uncolor(out)
    assert '''
tracing: circular-dep-a
already queued: circular-dep-b==1.0 (from circular-dep-a)
tracing: circular-dep-b==1.0 (from circular-dep-a)
''' in out

    frozen_requirements = pip_freeze(str(venv)).split('\n')
    assert 'circular-dep-a==1.0' in frozen_requirements
    assert 'circular-dep-b==1.0' in frozen_requirements


@pytest.mark.usefixtures('pypi_server')
@pytest.mark.skipif(
    sys.version_info > (3, 0),
    reason='ancient versions are not py3 compatible, even for install',
)
@pytest.mark.parametrize('reqs', [
    # new setuptools and old pip
    [
        'setuptools==18.2',
        # Non-SNI compatible clients (i.e. pip<2.7.9) cannot access public pypi anymore.
        # pip==6.0 is the earliest supported version. See https://github.com/pypa/pypi-support/issues/978
        'pip==6.0',
    ],
])
def test_old_pip_and_setuptools(tmpdir, reqs):
    """We should be able to use pip-faster's wheel building even if we have
    ancient pip and setuptools.

    https://github.com/Yelp/venv-update/issues/33
    """
    tmpdir.chdir()

    # 1. Create an empty virtualenv.
    # 2. Install old pip/setuptools that don't support wheel building.
    # 3. Install pip-faster.
    # 4. Install pure-python-package and assert it was wheeled during install.
    tmpdir.join('venv')
    venv = Path('venv')
    run('virtualenv', venv.strpath)

    # We need to add public PyPI as an extra URL since we're installing
    # packages (setuptools and pip) which aren't available from our PyPI fixture.
    from os import environ
    environ['PIP_EXTRA_INDEX_URL'] = 'https://pypi.org/simple/'
    try:
        pip = venv.join('bin/pip').strpath
        for req in reqs:
            run(pip, 'install', '--', req)
        run(pip, 'install', 'venv-update==' + __version__)
    finally:
        del environ['PIP_EXTRA_INDEX_URL']

    run(str(venv.join('bin/pip-faster')), 'install', 'pure_python_package')

    # it was installed
    assert 'pure-python-package==0.2.1' in pip_freeze(str(venv)).split('\n')

    # it was wheeled
    wheel_names = [wheel.name for wheel in cached_wheels(tmpdir)]
    assert 'pure-python-package' in wheel_names


@pytest.mark.usefixtures('tmpdir')
def test_install_whl_over_http(pypi_server):
    whl_url = pypi_server + '/packages/wheeled_package-0.2.0-py2.py3-none-any.whl'
    venv = make_venv()

    out, err = run(str(venv.join('bin/pip-faster')), 'install', whl_url)
    err = strip_pip_warnings(err)
    assert err == ''
    out = uncolor(out)
    assert out == '''\
Looking in indexes: {server}/simple
Collecting wheeled-package==0.2.0 from {server}/packages/wheeled_package-0.2.0-py2.py3-none-any.whl
  Downloading {server}/packages/wheeled_package-0.2.0-py2.py3-none-any.whl
Installing collected packages: wheeled-package
Successfully installed wheeled-package-0.2.0
'''.format(server=pypi_server)
