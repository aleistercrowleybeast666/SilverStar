"""Late legal JY streams exercise the generated parser, controller and adapter."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


def _ProjectGet(tmp_path, workspace_root):
    configured = os.environ.get("SILVERSTAR_BOOT_PROBE_PROJECT")
    if configured is not None:
        return Path(configured)
    from silverstar_fccg.app.service import FccgService
    service = FccgService(workspace_root)
    project = tmp_path / "BootProbe"
    service.Project_Save(
        service.ReferenceProject_Create("BootProbe"), project,
        confirm_dangerous=True,
    )
    return project


def _CompilerCommand(project):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    command = [
        compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-include",
        str(project / "Generated/Inc/project_flight_config.h"),
    ]
    for path in project.rglob("Inc"):
        if "build" not in path.relative_to(project).parts:
            command += ["-I", str(path)]
    command += ["-I", str(project / "Tests/Host"),
                "-I", str(project / "System/User")]
    return command


def _CompileAndRun(command, project, executable):
    result = subprocess.run(
        command + ["-o", str(executable)], cwd=project,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(
        [str(executable)], cwd=project, capture_output=True,
        text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_jy901b_late_stream_and_probe_budget(tmp_path, workspace_root):
    project = _ProjectGet(tmp_path, workspace_root)
    command = _CompilerCommand(project) + [
        "-DJY_BOOT_PROBE_ADAPTER_VERIFY=1", "-ffunction-sections",
        "-fdata-sections", "-Wl,--gc-sections",
    ]
    sources = [
        "Tests/Host/host_platform_mock.c",
        "Common/Src/common_ringbuf.c",
        "Common/Src/silverstar_assert.c",
        "Generated/Src/project_resources.c",
        "Devices/IMU/JY901B/Src/jy901b_device.c",
        "Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c",
        "Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c",
        "Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c",
        "System/Src/system_device_startup.c",
    ]
    command += [str(project / source) for source in sources]
    # Use the current owning test against either the pre-fix or final firmware.
    command += [str(workspace_root / (
        "plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/"
        "test_jy901b_startup.c")), "-lm"]
    _CompileAndRun(command, project, tmp_path / "jy-boot-probe.exe")


def test_outer_startup_keeps_delegated_busy_pending(tmp_path, workspace_root):
    project = _ProjectGet(tmp_path, workspace_root)
    command = _CompilerCommand(project) + [
        "-DSYSTEM_GNSS_BOOT_WRITE_CONFIG=1U",
        "-DSYSTEM_GNSS_BOOT_VERIFY_CONFIG=0U",
        "-DSYSTEM_IMU_BOOT_VERIFY_CONFIG=0U",
    ]
    core = workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload"
    command += [
        str(core / "Tests/Host/test_system_startup.c"),
        str(project / "System/Src/system_startup.c"),
        str(project / "Common/Src/silverstar_assert.c"),
    ]
    _CompileAndRun(command, project, tmp_path / "outer-startup.exe")
