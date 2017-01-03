from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import os
import time
from subprocess import CalledProcessError

import pytest

import testing as T
from testing.python_lib import PYTHON_LIB


def assert_venv_marked_invalid(venv):
    """we mark a virtualenv as invalid by bumping its timestamp back by a day"""
    venv_age = time.time() - os.path.getmtime(venv.strpath)
    assert venv_age / 60 / 60 / 24 > 1


@pytest.mark.usefixtures('pypi_server')
def test_conflicting_reqs(tmpdir):
    tmpdir.chdir()
    T.requirements('''
dependant_package
conflicting_package
''')

    with pytest.raises(CalledProcessError) as excinfo:
        T.venv_update()
    assert excinfo.value.returncode == 1
    out, err = excinfo.value.result

    err = T.strip_coverage_warnings(err)
    err = T.strip_pip_warnings(err)
    assert err == ('''\
Error: version conflict: many-versions-package 3 (venv/{python_lib})'''
''' <-> many-versions-package<2 (from conflicting_package->-r requirements.txt (line 3))
''').format(python_lib=PYTHON_LIB)
    out = T.uncolor(out)
    assert out.endswith('''

Something went wrong! Sending 'venv' back in time, so make knows it's invalid.
''')

    assert_venv_marked_invalid(tmpdir.join('venv'))


@pytest.mark.usefixtures('pypi_server')
def test_multiple_issues(tmpdir):
    # Make it a bit worse. The output should show all three issues.
    tmpdir.chdir()
    T.enable_coverage()

    T.requirements('dependant_package\n-r %s/requirements.d/coverage.txt' % T.TOP)
    T.venv_update()

    T.run('./venv/bin/pip', 'uninstall', '--yes', 'implicit_dependency')
    T.requirements('''
dependant_package
conflicting_package
pure_python_package==0.1.0
''')

    with pytest.raises(CalledProcessError) as excinfo:
        T.venv_update()
    assert excinfo.value.returncode == 1
    out, err = excinfo.value.result

    err = T.strip_coverage_warnings(err)
    assert err == ('''\
Error: version conflict: pure-python-package 0.1.0 (venv/{python_lib})'''
        ''' <-> pure-python-package>=0.2.1 (from dependant_package->-r requirements.txt (line 2))
Error: version conflict: many-versions-package 3 (venv/{python_lib})'''
        ''' <-> many-versions-package<2 (from conflicting_package->-r requirements.txt (line 3))
''').format(python_lib=PYTHON_LIB)
    out = T.uncolor(out)
    assert out.endswith(
        '''

Something went wrong! Sending 'venv' back in time, so make knows it's invalid.
''')

    assert_venv_marked_invalid(tmpdir.join('venv'))


@pytest.mark.usefixtures('pypi_server')
def test_editable_egg_conflict(tmpdir):
    tmp_conflicting_package = 'tmp/conflicting_package'
    conflicting_package = tmpdir / tmp_conflicting_package
    many_versions_package_2 = tmpdir / 'tmp/many_versions_package_2'

    from shutil import copytree
    copytree(
        str(T.TOP / 'tests/testing/packages/conflicting_package'),
        str(conflicting_package),
    )

    copytree(
        str(T.TOP / 'tests/testing/packages/many_versions_package_2'),
        str(many_versions_package_2),
    )

    with many_versions_package_2.as_cwd():
        from sys import executable as python
        T.run(python, 'setup.py', 'bdist_egg', '--dist-dir', str(conflicting_package))

    with tmpdir.as_cwd():
        T.enable_coverage()
        T.requirements('-e %s' % conflicting_package)
        with pytest.raises(CalledProcessError) as excinfo:
            T.venv_update()
        assert excinfo.value.returncode == 1
        out, err = excinfo.value.result

        err = T.strip_coverage_warnings(err)
        err = T.strip_pip_warnings(err)
        if True:  # :pragma:nocover:pylint:disable=using-constant-test
            # Debian de-vendorizes the version of pip it ships
            try:
                from sysconfig import get_python_version
            except ImportError:  # <= python2.6
                from distutils.sysconfig import get_python_version
        assert err == ('''\
Error: version conflict: many-versions-package 2 ({0}/many_versions_package-2-py{1}.egg)'''
''' <-> many_versions_package<2 (from conflicting-package==1->-r requirements.txt (line 1))
''').format(tmp_conflicting_package, get_python_version())

        out = T.uncolor(out)
        expected = '\nSuccessfully installed conflicting-package many-versions-package-1\n'
        assert expected in out
        rest = out.rsplit(expected, 1)[-1]

        assert (
            '''\

Something went wrong! Sending 'venv' back in time, so make knows it's invalid.
'''
        ) == rest

        assert_venv_marked_invalid(tmpdir.join('venv'))
