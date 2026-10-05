"""Revision metadata must describe the actual preserved KF6 source."""
import hashlib

import pytest

from silverstar_fccg.generator.kf6_identity import (
    COMPONENT, KERNEL_PATHS, Kf6Identity_Validate,
)


def test_kf6_preserved_kernel_identity(tmp_path):
    files = {}
    for relative in KERNEL_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = {"components": {COMPONENT: {"files": files}}}
    Kf6Identity_Validate(tmp_path, previous, {"files": files})
    before = {p: (tmp_path / p).read_bytes() for p in files}
    upstream = dict(files)
    upstream[KERNEL_PATHS[1]] = "0" * 64
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": upstream})
    assert before == {p: (tmp_path / p).read_bytes() for p in files}
    (tmp_path / KERNEL_PATHS[2]).write_bytes(b"user-owned edit")
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": files})
    assert (tmp_path / KERNEL_PATHS[2]).read_bytes() == b"user-owned edit"
    (tmp_path / KERNEL_PATHS[2]).unlink()
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": files})


def test_kf6_fresh_project_identity(tmp_path):
    Kf6Identity_Validate(tmp_path, {}, {"files": {}})
