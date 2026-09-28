from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_kf6_integrity_streaming_closure_and_recovery(tmp_path: Path) -> None:
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    kf6 = root / "plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6"
    common = root / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
    executable = tmp_path / "navigation-integrity-host.exe"
    command = [
        gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I" + str(kf6 / "Inc"), "-I" + str(common / "Inc"),
        str(kf6 / "Src/navigation_integrity.c"),
        str(common / "Src/silverstar_assert.c"),
        str(root / "tests/fixtures/navigation_integrity_host.c"),
        "-lm", "-o", str(executable),
    ]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
    result = subprocess.run([str(executable)], check=False, capture_output=True, text=True,
                            env=environment)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "8 scenarios, 0 failures" in result.stdout
