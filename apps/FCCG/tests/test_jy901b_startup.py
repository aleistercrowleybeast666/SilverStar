"""Exercise the JY901B startup path with the real driver and host UART mock."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_jy901b_startup(tmp_path: Path) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    builtin = Path(__file__).resolve().parents[1] / "plugins" / "builtin"
    core = builtin / "silverstar_core_0_1_0" / "payload"
    jy = builtin / "silverstar_device_imu_jy901b" / "payload"
    mcu = builtin / "silverstar_mcu_stm32f407vet6" / "payload"
    fixture = core / "Tests" / "Host" / "Fixtures" / "MultiInstance"
    executable = tmp_path / "jy901b_startup.exe"
    command = [
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(fixture / "Inc"),
        "-I", str(mcu / "Platform" / "Inc"),
        "-I", str(core / "System" / "Inc"),
        "-I", str(core / "Interfaces" / "Inc"),
        "-I", str(core / "Common" / "Inc"),
        "-I", str(core / "Tests" / "Host"),
        "-I", str(jy / "Devices" / "IMU" / "JY901B" / "Inc"),
        "-I", str(jy / "Devices" / "IMU" / "JY901B" / "Adapter" / "Inc"),
        str(core / "System" / "Src" / "system_device_startup.c"),
        str(core / "Common" / "Src" / "silverstar_assert.c"),
        str(core / "Tests" / "Host" / "host_platform_mock.c"),
        str(fixture / "multi_instance_resources.c"),
        str(jy / "Devices" / "IMU" / "JY901B" / "Src" / "jy901b_device.c"),
        str(jy / "Devices" / "IMU" / "JY901B" / "Adapter" / "Src" / "jy901b_startup.c"),
        str(core / "Tests" / "Host" / "test_jy901b_startup.c"),
        "-lm", "-o", str(executable),
    ]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([executable], capture_output=True, text=True)
    assert executed.returncode == 0, executed.stdout + executed.stderr
