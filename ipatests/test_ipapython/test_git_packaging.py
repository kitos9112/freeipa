# Copyright (C) 2026 FreeIPA Contributors see COPYING for license
"""Build administration wheels without Autoconf-generated checkout files."""

from pathlib import Path
from importlib.util import find_spec
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    'ipasetup.py.in', 'ipasetup_git.py', 'VERSION.m4', 'API.txt', 'COPYING',
)


@pytest.mark.skipif(
    not all((ROOT / name).is_file() for name in INPUTS)
    or find_spec('pip') is None or find_spec('wheel') is None,
    reason='requires complete Git checkout and pip/wheel build tools',
)
@pytest.mark.parametrize('package', [
    'ipaclient', 'ipalib', 'ipaplatform', 'ipapython',
])
def test_clean_git_wheel(tmp_path, package):
    root = ROOT
    for name in INPUTS:
        shutil.copy2(root / name, tmp_path / name)
    shutil.copytree(
        root / package, tmp_path / package,
        ignore=shutil.ignore_patterns(
            'build', '*.egg-info', '__pycache__', 'version.py', 'override.py',
        ),
    )
    result = subprocess.run([
        sys.executable, '-m', 'pip', 'wheel', '--no-deps',
        '--no-build-isolation', str(tmp_path / package),
        '--wheel-dir', str(tmp_path / 'wheels'),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheel, = (tmp_path / 'wheels').glob('*.whl')
    assert 'transficc' in wheel.name
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any('/install/' in name for name in names)
        assert 'ipaplatform/override.py' not in names
        if package == 'ipapython':
            metadata, = (name for name in names
                         if name.endswith('.dist-info/METADATA'))
            assert 'Requires-Dist: packaging' in archive.read(metadata).decode()
            version = archive.read('ipapython/version.py').decode('utf-8')
            assert '@VERSION@' not in version
            assert '2.258' in version
            assert 'dnsrecord_show/1' in version
        elif package == 'ipaplatform':
            assert 'ipaplatform/macos/tasks.py' in names
