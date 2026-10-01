"""Real JY901B driver: clock, output readback and UART recovery contracts."""
import shutil
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def jy_boundary_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    builtin = root / "plugins/builtin"
    core = builtin / "silverstar_core_0_1_0/payload"
    jy = builtin / "silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B"
    fixture = core / "Tests/Host/Fixtures/MultiInstance"
    exe = tmp_path_factory.mktemp("jy-boundary") / "boundary.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    source = Path(os.environ.get("SILVERSTAR_JY_TEST_SOURCE", str(jy / "Src")))
    for path in [source, fixture / "Inc", builtin / "silverstar_platform_api/payload/Platform/Inc",
                 core / "System/Inc", core / "Interfaces/Inc", core / "Common/Inc",
                 core / "Tests/Host", jy / "Inc", jy / "Src", jy / "Adapter/Inc"]:
        command += ["-I", str(path)]
    command += [str(core / "Tests/Host/host_platform_mock.c"),
                str(fixture / "multi_instance_resources.c"),
                str(core / "Common/Src/silverstar_assert.c"),
                str(root / "tests/fixtures/jy901b_boundary_host.c"), "-lm", "-o", str(exe)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


@pytest.mark.parametrize("group,scenario", [
    *(('time', s) for s in ['normal', 'cross_ms', 'no_frame', 'timeout', 'wrap_to_zero', 'wrap_elapsed']),
    *(('readback', s) for s in ['only_quat', 'missing_acc', 'missing_gyro', 'missing_pressure',
                              'missing_quat', 'complete', 'complete_extra', 'already_complete']),
    *(('receive', s) for s in ['normal', 'stop_fail', 'restart_fail', 'tx_fail',
                             'tx_fail_restart_fail', 'baud_normal', 'baud_stop_fail', 'baud_restart_fail']),
    *(('save', s) for s in ['normal', 'stop_fail', 'restart_fail', 'unlock_fail',
                          'unlock_fail_restart_fail', 'save_fail', 'save_fail_restart_fail']),
])
def test_jy901b_boundary(jy_boundary_executable, group, scenario):
    result = subprocess.run([str(jy_boundary_executable), group, scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
