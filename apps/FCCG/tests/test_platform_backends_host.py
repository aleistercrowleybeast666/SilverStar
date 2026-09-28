from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_f407_platform_backends_compile_and_pass_host_boundaries(
    workspace_root: Path, tmp_path: Path
) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    executable = tmp_path / "platform_backends.exe"
    command = [
        compiler,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        f"-I{workspace_root / 'tests' / 'host_platform'}",
        f"-I{workspace_root / 'tools' / 'reference_overlays' / 'platform'}",
        f"-I{workspace_root / 'plugins' / 'builtin' / 'silverstar_mcu_stm32f407vet6' / 'payload' / 'Platform' / 'Inc'}",
        str(workspace_root / "tools" / "reference_overlays" / "platform" / "platform_i2c_stm32f4.c"),
        str(workspace_root / "tools" / "reference_overlays" / "platform" / "platform_can_stm32f4.c"),
        str(workspace_root / "tools" / "reference_overlays" / "platform" / "platform_pwm_stm32f4.c"),
        str(workspace_root / "tests" / "host_platform" / "test_platform_backends.c"),
        "-o",
        str(executable),
    ]
    compile_result = subprocess.run(
        command,
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    run_result = subprocess.run(
        [str(executable)],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr
