"""Test-only directory creation without chmod/ACL operations on this host.

pytest 9 on Python 3.14 creates mode-0700 directories that are unreadable in
this restricted Windows executor. Use unique normal-inherited directories;
never relax the sandbox or change an existing directory's permissions.
"""
from pathlib import Path
from uuid import uuid4

import pytest

@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    root = Path(config.option.basetemp).resolve()
    root.mkdir(parents=True, exist_ok=False)
    factory = config._tmp_path_factory
    factory._basetemp = root
    def mktemp(basename, numbered=True):
        name = basename + ('_' + uuid4().hex[:8] if numbered else '')
        path = root / name
        if path.parent != root or not name:
            raise ValueError('unsafe_test_directory')
        path.mkdir()
        return path
    factory.mktemp = mktemp
