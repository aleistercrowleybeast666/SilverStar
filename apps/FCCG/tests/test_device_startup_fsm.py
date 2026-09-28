"""Compile the firmware startup controller against a host C test driver."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_device_startup_state_machine(tmp_path: Path) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    payload = (
        Path(__file__).resolve().parents[1]
        / "plugins/builtin/silverstar_core_0_1_0/payload"
    )
    executable = tmp_path / "device_startup_fsm.exe"
    command = [
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(payload / "System/Inc"),
        str(payload / "System/Src/system_device_startup.c"),
        str(payload / "Tests/Host/test_device_startup_fsm.c"),
        "-o", str(executable),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    subprocess.run([executable], check=True, capture_output=True, text=True)
