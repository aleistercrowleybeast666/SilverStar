"""Exercise signed NAV-PVT velocity boundaries through the actual adapter."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("optimization", ["-O0", "-O2"])
def test_neo_m9n_velocity_boundaries(tmp_path: Path, optimization: str) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    builtin = Path(__file__).resolve().parents[1] / "plugins" / "builtin"
    core = builtin / "silverstar_core_0_1_0" / "payload"
    platform = builtin / "silverstar_platform_api" / "payload" / "Platform"
    device = (builtin / "silverstar_device_gnss_neo_m9n" / "payload"
              / "Devices" / "GNSS" / "NEO_M9N")
    fixture = core / "Tests" / "Host" / "Fixtures" / "MultiInstance"
    includes = [
        fixture / "Inc", platform / "Inc", core / "System" / "Inc",
        core / "System" / "User", core / "Interfaces" / "Inc",
        core / "Common" / "Inc", core / "Tests" / "Host",
        device / "Inc", device / "Adapter" / "Inc",
        builtin / "silverstar_mcu_stm32f407vet6" / "payload"
        / "Targets" / "SilverStar_F407" / "Inc",
    ]
    includes.extend(path for path in sorted(core.rglob("Inc")) if path not in includes)
    includes.append(builtin / "silverstar_algorithm_alignment_common" / "payload"
                    / "Algorithm" / "Alignment" / "Common" / "Inc")
    includes.append(builtin / "silverstar_device_imu_jy901b" / "payload"
                    / "Devices" / "IMU" / "JY901B" / "Adapter" / "Inc")
    includes.append(builtin / "silverstar_device_imu_jy901b" / "payload"
                    / "Devices" / "IMU" / "JY901B" / "Inc")
    sources = [
        core / "Tests" / "Host" / "test_neo_m9n_adapter.c",
        core / "Tests" / "Host" / "host_platform_mock.c",
        fixture / "multi_instance_resources.c",
        core / "System" / "Src" / "system_device_startup.c",
        core / "System" / "Src" / "system_gnss_quality.c",
        core / "Common" / "Src" / "silverstar_assert.c",
        device / "Src" / "neo_m9n_device.c",
        device / "Adapter" / "Src" / "neo_m9n_system_adapter.c",
        device / "Adapter" / "Src" / "neo_m9n_startup.c",
    ]
    executable = tmp_path / "neo_m9n_velocity.exe"
    command = [
        compiler, "-std=c11", optimization, "-Wall", "-Wextra", "-Werror",
        # Host composition facts only; no mission-action implementation is linked.
        "-DMISSION_ACTION_OUTPUT_BUILD_START_ACTION_AVAILABLE=1U",
        "-DMISSION_ACTION_OUTPUT_BUILD_PARACHUTE_DEPLOY_AVAILABLE=1U",
        "-DSYSTEM_INDICATOR_SYSTEM_ENABLE=0U",
        "-fsanitize=signed-integer-overflow", "-fsanitize-undefined-trap-on-error",
        *["-I" + str(path) for path in includes],
        *map(str, sources), "-lm", "-o", str(executable),
    ]
    compiled = subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    executed = subprocess.run(
        [executable], capture_output=True, text=True, timeout=30, check=False
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert "velD=-2147483648 mm/s -> U=" in executed.stdout
