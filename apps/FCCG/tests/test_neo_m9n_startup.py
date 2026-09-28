"""Run the M9N host protocol and startup suite against current plugin sources."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_neo_m9n_startup(tmp_path: Path) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    builtin = Path(__file__).resolve().parents[1] / "plugins" / "builtin"
    core = builtin / "silverstar_core_0_1_0" / "payload"
    m9 = builtin / "silverstar_device_gnss_neo_m9n" / "payload"
    mcu = builtin / "silverstar_mcu_stm32f407vet6" / "payload"
    fixture = core / "Tests" / "Host" / "Fixtures" / "MultiInstance"
    device = m9 / "Devices" / "GNSS" / "NEO_M9N"
    executable = tmp_path / "neo_m9n_startup.exe"
    command = [
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-DPROJECT_RESOURCE_GNSS_UART=PLATFORM_UART_1",
        "-I", str(fixture / "Inc"),
        "-I", str(mcu / "Platform" / "Inc"),
        "-I", str(core / "System" / "Inc"),
        "-I", str(core / "Interfaces" / "Inc"),
        "-I", str(core / "Common" / "Inc"),
        "-I", str(core / "Tests" / "Host"),
        "-I", str(device / "Inc"),
        "-I", str(device / "Adapter" / "Inc"),
        str(core / "System" / "Src" / "system_device_startup.c"),
        str(core / "Common" / "Src" / "silverstar_assert.c"),
        str(fixture / "multi_instance_resources.c"),
        str(device / "Src" / "neo_m9n_device.c"),
        str(device / "Adapter" / "Src" / "neo_m9n_startup.c"),
        str(core / "Tests" / "Host" / "test_neo_m9n_device.c"),
        "-lm", "-o", str(executable),
    ]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([executable], capture_output=True, text=True)
    assert executed.returncode == 0, executed.stdout + executed.stderr
