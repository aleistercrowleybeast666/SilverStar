"""Independent RF56 actual-rate/START qualification; original stress is unchanged."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from run_storage_integrity import StorageContract_DefinitionsGet


def RfActualRates_Run(project: Path, compiler: str) -> int:
    project = project.resolve()
    fixture = Path(__file__).resolve().parent
    output = project / "build/FCCG/Host/Tests/RfActualRates56"
    output.mkdir(parents=True, exist_ok=True)
    graph = (project / "Generated/project_sources.mk").read_text(encoding="utf8")
    definitions = StorageContract_DefinitionsGet(graph)
    model = json.loads((project / "SilverStar.ssproject").read_text(encoding="utf8"))
    if model["build"]["target_profile"] != "SilverStar_F103RF":
        raise ValueError("This named qualification fixture requires the actual RF project")
    if definitions.get("SYSTEM_BUILD_FUSION_ALGORITHM") != "-DSYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_SF6":
        raise ValueError("SF6 must be selected by the generated SourceGraph")
    disk_paths = re.findall(r"^\s+(Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight\.c)\s*\\?\s*$", graph, re.MULTILINE)
    if len(disk_paths) != 1:
        raise ValueError("Exactly one declared real F1 diskio is required")
    disk = project / disk_paths[0]
    (output / "sd_diskio.c").write_bytes(disk.read_bytes())
    config = (project / "HardwareGenerated/STM32CubeMX/FATFS/Target/ffconf.h").read_text(encoding="utf8")
    for header in ("main.h", "stm32f1xx_hal.h", "bsp_driver_sd.h"):
        config = config.replace(f'#include "{header}"', "")
    (output / "ffconf.h").write_text(config, encoding="utf8")
    fatfs = project / "Middlewares/Third_Party/FatFs/src"
    includes = [output, fixture, fatfs, project / "Protocol/SSLOG/Inc", project / "Common/Inc", project / "Platform/Inc"]
    host = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf8")
    includes += [project / relative.replace("\\", "/") for relative in re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"', host)]
    includes.insert(0, project / "Targets/SilverStar_F103RF/Inc")
    includes += [project / "Devices/Storage/SdSdioFatFs/Adapter/Inc", project / "Devices/Storage/SdSdioFatFs/Inc"]
    sources = [fixture / "test_rf_actual_rates_storage.c", output / "sd_diskio.c"]
    sources += [fatfs / name for name in ("ff.c", "ff_gen_drv.c", "diskio.c")]
    sources += [project / relative for relative in (
        "Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c",
        "Protocol/SSLOG/Src/sslog_protocol.c", "Protocol/SSLOG/Src/sslog_records.c",
        "Common/Src/silverstar_assert.c", "Tests/Target/storage_integrity.c",
        "APP/Src/device_native_log.c", "APP/Src/imu_sample_bus.c",
        "System/Calibration/Src/system_calibration_correction.c",
        "System/Calibration/Src/system_mag_calibration.c",
        "APP/Src/logger_bus.c", "APP/Src/logger_task.c", "Common/Src/common_spsc_queue.c",
        "System/Src/system_log_policy.c", "System/Src/system_profile.c",
        "System/Src/system_navigation_profile.c", "System/Src/system_estimator_profile.c",
        "Generated/Src/project_metadata.c", "Generated/Src/project_log_config.c",
        "Generated/Src/project_mission_parameters.c", "Generated/Src/project_log_decoder_profile.c",
        "Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c",
        "Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c",
        "Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c",
        "Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c",
        "Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c",
        "Devices/Storage/SdSdioFatFs/Adapter/Src/log_sink_service.c",
        "Algorithm/Estimator/SF6/Src/navigation_sf6.c",
        "Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c",
        "Algorithm/Common/Src/geodesy_local.c", "Algorithm/Common/Src/attitude_frame.c",
        "Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
        "APP/Src/estimator_bus.c", "System/Src/system_navigation_health.c",
        "System/Src/system_gnss_quality.c", "System/Src/system_barometer.c", "System/Src/system_time.c")]
    # Same declared logical-source limitation as the existing storage helper.
    # No MPU interrupt/physical epoch evidence is supplied by this Host fixture.
    definitions["SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED"] = "-DSYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED=0U"
    definitions["SYSTEM_LOG_RECORD_QUEUE_DEPTH"] = "-DSYSTEM_LOG_RECORD_QUEUE_DEPTH=56U"
    definitions["SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH"] = "-DSYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH=16U"
    binary = output / "rf_actual_rates_storage.exe"
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-Wno-unused-variable", "-Wno-pointer-to-int-cast", "-ffunction-sections", "-fdata-sections",
               "-Wl,--gc-sections", "-DSILVERSTAR_HOST_FATFS_R011=1", "-D__IO=volatile",
               "-D__weak=__attribute__((weak))", "-include", "stdint.h",
               "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-Wl,--wrap=" + name for name in (
        "SystemTime_GetMonotonicUs", "vTaskDelay", "xQueueReceive", "CommonSpscQueue_Push",
        "FlightLog_RecordSerialize", "f_sync", "LoggerBus_StartDurable", "main")]
    command += list(definitions.values()) + ["-I" + str(path) for path in includes]
    fixture_object = output / "rf_actual_rates_fixture.o"
    # Only this Host TU uses LTO to discard unexecuted Flight task services on
    # MinGW. Product callees stay non-LTO so linker interception is observable.
    fixture_command = [arg for arg in command if not arg.startswith("-Wl,")]
    fixture_command += ["-flto=2", "-fno-inline", "-c", str(sources[0]), "-o", str(fixture_object)]
    command += [str(fixture_object)] + [str(path) for path in sources[1:]] + ["-lm", "-o", str(binary)]
    environment = dict(os.environ, TEMP=str(output), TMP=str(output), PYTHONIOENCODING="utf-8")
    commands = []
    receipts = output / "Receipts"
    receipts.mkdir(exist_ok=True)
    attempt = receipts / f"attempt{len(list(receipts.glob('attempt*'))) + 1:03d}"
    attempt.mkdir()
    def run(name: str, argv: list[str]) -> int:
        start = datetime.now(timezone.utc).isoformat()
        log = attempt / (name + ".log")
        with log.open("w", encoding="utf8") as stream:
            result = subprocess.run(argv, cwd=project, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        commands.append({"name": name, "argv": argv, "cwd": str(project), "exit": result.returncode,
                         "start_utc": start, "end_utc": datetime.now(timezone.utc).isoformat(),
                         "log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        (attempt / "commands.json").write_text(json.dumps(commands, indent=2), encoding="utf8")
        print(f"RF_ACTUAL_PROGRESS name={name} exit={result.returncode}", flush=True)
        print(log.read_text()[-4200:], flush=True)
        return result.returncode
    rc = run("fixture-compile", fixture_command)
    if rc == 0:
        rc = run("compile", command)
    if rc != 0:
        return rc
    inputs = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    inputs.update({str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        fixture / "test_logger_storage.c", fixture / "test_storage_integrity.c", fixture / "test_sparse_preflight.h",
        project / "APP/Src/flight_task.c", project / "Generated/project_sources.mk", project / "SilverStar.ssproject")})
    (attempt / "source_inputs.json").write_text(json.dumps({"inputs": inputs, "definitions": definitions,
        "scope": "Actual RF logical-rate fixture; original stress untouched; no ARM/hardware action",
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}, indent=2), encoding="utf8")
    baseline = attempt / "rf-actual-rates-baseline.sslog"
    baseline_rc = run("actual-rates-baseline", [str(binary), str(baseline), "actual-rates-baseline"])
    normal = attempt / "rf-actual-rates-delay80.sslog"
    normal_rc = run("actual-rates", [str(binary), str(normal), "actual-rates"])
    fault_rc = run("start-sync-error", [str(binary), str(attempt / "rf-fault-unused.sslog"), "start-sync-error"])
    decoders = list(project.glob("*.ssdecoder"))
    if len(decoders) != 1:
        raise ValueError("The exact generated decoder is required")
    auditor = project / "Tools/sslog_audit.py"
    audit_baseline_rc = audit_delay_rc = 1
    if baseline.is_file():
        audit_baseline_rc = run("strict-audit-baseline", [sys.executable, str(auditor), str(baseline), "--decoder", str(decoders[0])])
    if normal.is_file():
        audit_delay_rc = run("strict-audit-delay80", [sys.executable, str(auditor), str(normal), "--decoder", str(decoders[0])])
        # Diagnostic-only explicit-drop audit never changes the strict result.
        run("drop-accounting-audit-delay80", [sys.executable, str(auditor), str(normal), "--decoder", str(decoders[0]), "--allow-queue-drops"])
    for name in ("actual-rates-baseline", "actual-rates"):
        trace = (attempt / (name + ".log")).read_text()
        if "RF_FINAL " not in trace or "RF_START_DURABLE " not in trace:
            raise ValueError("Actual independently named fixture/critical checks did not complete: " + name)
    if "RF_EXPECTED_SYNC_FAULT " not in (attempt / "start-sync-error.log").read_text():
        raise ValueError("Fault test did not prove absent START acknowledgement")
    return baseline_rc or normal_rc or fault_rc or audit_baseline_rc or audit_delay_rc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    raise SystemExit(RfActualRates_Run(args.project, args.compiler))
