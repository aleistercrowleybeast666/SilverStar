"""Actual C compact MPU recovery against bounded Host I2C/time mocks."""
import json
import hashlib
from dataclasses import replace
import os
from pathlib import Path
import subprocess

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.generator.render import _DeviceBuildCapabilitiesHeader_Render, _DeviceInstancesHeader_Render, _DeviceInstancesSource_Render, _FlightConfigHeader_Render

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload"
BUILTIN = ROOT / "apps/SCG/plugins/builtin"
FIXTURE = Path(__file__).parent / "fixtures/mpu_recovery"
SEQUENCES = (
    "probe_failure_then_recovery", "reset_write_failure_then_recovery",
    "reset_timeout_then_recovery", "readback_failure_then_recovery",
    "sample_verify_timeout_then_recovery", "unlimited_attempts_saturated_backoff",
    "millisecond_wrap_backoff", "prestart_source_lock", "poststart_same_source_lock",
    "stale_sample_and_profile_revoked", "new_epoch_mount_and_metadata",
    "stop_cancels_retry", "history_report_remains_failed", "calibration_alignment_origin_not_ready",
)


def compile_fixture(directory: Path, *, compact: bool, baseline: bool = False) -> Path:
    service = FccgService(ROOT / "apps/SCG")
    model = ProjectModel_Load(ROOT / ".work/generated_ret6/SilverStar.ssproject")
    catalog = service.catalog.ProjectView_Get(model)
    model.build = replace(model.build, compact_mode=compact,
                          feature_tier="minimal" if compact else "full")
    build_mode = _DeviceBuildCapabilitiesHeader_Render(model, catalog)
    assert f"#define SILVERSTAR_BUILD_COMPACT_ENABLED {int(compact)}U" in build_mode
    (directory / "project_device_build_capabilities.h").write_text(build_mode, encoding="utf-8")
    (directory / "project_flight_config.h").write_text(_FlightConfigHeader_Render(model, catalog), encoding="utf-8")
    (directory / "project_device_instances.h").write_text(_DeviceInstancesHeader_Render(model, catalog), encoding="utf-8")
    facade = directory / "project_device_instances.c"
    facade.write_text(_DeviceInstancesSource_Render(model, catalog), encoding="utf-8")
    sensor = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    mpu = BUILTIN / "silverstar_device_imu_mpu6050/payload/Devices/IMU/MPU6050"
    sources = [facade, sensor / "Src/sensor_register_bus.c", sensor / "Src/sensor_imu.c",
               sensor / "Adapter/Src/sensor_imu_adapter.c", mpu / "Src/mpu6050_device.c",
               mpu / "Adapter/Src/mpu6050_instance.c", CORE / "System/Src/system_source_selector.c",
               CORE / "Common/Src/silverstar_assert.c", FIXTURE / "test_mpu_recovery.c"]
    if compact:
        sources.append(CORE / "System/Src/system_health.c")
        sources.append(CORE / "System/Src/system_imu_epoch.c")
    includes = [FIXTURE, directory, ROOT / ".work/generated_ret6/Generated/Inc", CORE / "Interfaces/Inc", CORE / "System/Inc", CORE / "System/User", CORE / "Common/Inc"]
    for component in model.ComponentIds_Get():
        manifest = catalog.Component_Get(component)
        includes.extend(manifest.payload_root / relative for relative in manifest.build.include_dirs)
    binary = directory / "mpu_recovery.exe"
    command = [os.environ.get("HOST_GCC", "D:/msys64/ucrt64/bin/gcc.exe"), "-std=c11", "-O2", "-flto",
               "-Wall", "-Wextra", "-Werror", "-pedantic", "-ffunction-sections", "-fdata-sections",
               "-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0", "-DSYSTEM_BUILD_BAROMETER_COLD_ENABLED=1", "-Wl,--gc-sections",
               "-include", str(directory / "project_flight_config.h")]
    if not compact:
        command += ["-DTEST_ORDINARY=1"]
    if baseline:
        command += ["-DTEST_BASELINE=1"]
    command += ["-I" + str(path) for path in includes] + [str(source) for source in sources] + ["-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (directory / "compile.json").write_text(json.dumps({"argv": command, "exit": result.returncode,
        "build_mode": {"compact_mode": compact, "header": build_mode,
                       "header_sha256": hashlib.sha256((directory / "project_device_build_capabilities.h").read_bytes()).hexdigest()},
        "stdout": result.stdout, "stderr": result.stderr}, indent=2), encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return binary


def test_compact_mpu_fault_sequences(tmp_path: Path) -> None:
    binary = compile_fixture(tmp_path, compact=True)
    results = []
    for number, name in enumerate(SEQUENCES, 1):
        result = subprocess.run([str(binary), str(number)], capture_output=True, text=True, timeout=10)
        results.append({"number": number, "sequence": name, "exit": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
    (tmp_path / "sequences.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    assert all(row["exit"] == 0 for row in results), results


def test_ordinary_mpu_behavior_unchanged(tmp_path: Path) -> None:
    binary = compile_fixture(tmp_path, compact=False)
    results = []
    for number in (15, 16, 17):
        result = subprocess.run([str(binary), str(number)], capture_output=True, text=True, timeout=10)
        results.append({"number": number, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    (tmp_path / "ordinary_sequences.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    assert all(row["exit"] == 0 for row in results), results


def test_compact_mpu_prepared_config_intent(tmp_path: Path) -> None:
    binary = compile_fixture(tmp_path, compact=True)
    result = subprocess.run([str(binary), "18"], capture_output=True, text=True, timeout=10)
    record = {"case": 18, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    (tmp_path / "prepared_config_sequence.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    assert result.returncode == 0, record
