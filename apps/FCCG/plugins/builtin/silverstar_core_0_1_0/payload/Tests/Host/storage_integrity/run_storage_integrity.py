"""Build the real FatFs/diskio/codec with a delayed DMA Host model."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def StorageIntegrity_Run(project: Path, compiler: str) -> Path:
    fixture = Path(__file__).resolve().parent
    output = project / "build/FCCG/Host/Tests/StorageIntegrity"
    output.mkdir(parents=True, exist_ok=True)
    fatfs = project / "Middlewares/Third_Party/FatFs/src"
    diskio = project / "FATFS/Target/sd_diskio.c"
    # Copy byte-for-byte so quoted local vendor includes use the Host facade.
    (output / "sd_diskio.c").write_bytes(diskio.read_bytes())
    configuration = (project / "FATFS/Target/ffconf.h").read_text(encoding="utf-8")
    for header in ("main.h", "stm32f4xx_hal.h", "bsp_driver_sd.h"):
        configuration = configuration.replace(f'#include "{header}"', "")
    (output / "ffconf.h").write_text(configuration, encoding="utf-8")
    binary = output / "storage_integrity.exe"
    sources = [fixture / "test_storage_integrity.c", output / "sd_diskio.c",
               project / "Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c"]
    sources += [fatfs / name for name in ("ff.c", "ff_gen_drv.c", "diskio.c")]
    sources += [project / "Protocol/SSLOG/Src" / name for name in ("sslog_protocol.c", "sslog_records.c")]
    sources += [project / "Common/Src/silverstar_assert.c"]
    sources += [fixture.parent.parent / "Target/storage_integrity.c"]
    includes = [output, fixture, fatfs, project / "Protocol/SSLOG/Inc",
                project / "Common/Inc", project / "Platform/Inc"]
    flags = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
             "-Wno-unused-variable", "-Wno-pointer-to-int-cast"]
    command = list(flags)
    command += ["-I" + str(path) for path in includes]
    command += [str(path) for path in sources] + ["-lm", "-o", str(binary)]
    environment = dict(os.environ, TEMP=str(output), TMP=str(output))
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|PLAN|4", flush=True)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|BEGIN|1|4|compile", flush=True)
    subprocess.run(command, check=True, cwd=project, env=environment)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|DONE|1|4|compile", flush=True)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|BEGIN|2|4|byte-integrity", flush=True)
    log = output / "mixed.sslog"
    subprocess.run([str(binary), str(log)], check=True, cwd=project, env=environment)
    auditor = project / "Tools/sslog_audit.py"
    catalog = project / "Protocol/SSLOG/schema/sslog_schema.json"
    subprocess.run([sys.executable, str(auditor), str(log), "--catalog", str(catalog)],
                   check=True, cwd=project, env=environment)
    for mode in ("timeout-write", "timeout-read", "wrong-write", "wrong-read",
                 "start-write", "start-read", "sync-timeout"):
        subprocess.run([str(binary), str(log), mode], check=True, cwd=project, env=environment)
    subprocess.run([str(binary), "--target-bench"], check=True, cwd=project, env=environment)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|DONE|2|4|byte-integrity", flush=True)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|BEGIN|3|4|logger-compile", flush=True)
    logger_sources = [fixture / "test_logger_storage.c"] + sources[1:]
    logger_sources += [project / relative for relative in (
        "APP/Src/device_native_log.c", "APP/Src/imu_sample_bus.c",
        "System/Calibration/Src/system_calibration_correction.c",
        "System/Calibration/Src/system_mag_calibration.c",
        "APP/Src/logger_bus.c", "APP/Src/logger_task.c", "Common/Src/common_spsc_queue.c",
        "System/Src/system_log_policy.c", "System/Src/system_profile.c",
        "System/Src/system_navigation_profile.c", "System/Src/system_estimator_profile.c",
        "Generated/Src/project_metadata.c", "Generated/Src/project_log_config.c",
        "Generated/Src/project_mission_parameters.c",
        "Generated/Src/project_log_decoder_profile.c",
        "Devices/Storage/SdSdioFatFs/Src/storage_service.c",
        "Devices/Storage/SdSdioFatFs/Src/persistent_storage.c",
        "Devices/Storage/SdSdioFatFs/Src/mission_snapshot.c",
        "Devices/Storage/SdSdioFatFs/Src/mag_calibration_storage.c",
        "Devices/Storage/SdSdioFatFs/Src/log_sink_service.c")]
    # Reuse the generated Host include contract; never discover production sources.
    host_script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    host_includes = re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"', host_script)
    logger_includes = includes + [project / relative.replace("\\", "/") for relative in host_includes]
    logger_includes.append(project / "Devices/Storage/SdSdioFatFs/Inc")
    writer = output / "logger_storage.exe"
    command = flags + ["-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                       "-include", str(project / "Generated/Inc/project_flight_config.h")]
    source_graph = (project / "Generated/project_sources.mk").read_text(encoding="utf-8")
    for name in ("SYSTEM_BUILD_ESTIMATOR_ENABLED", "SYSTEM_BUILD_FUSION_ALGORITHM"):
        values = re.findall(r"^\s+" + name + r"=(\w+)\s*\\?\s*$", source_graph, re.MULTILINE)
        if len(values) != 1:
            raise ValueError(f"storage fixture requires one generated {name} definition")
        command.append(f"-D{name}={values[0]}")
    eskf_values = re.findall(r"^\s+SYSTEM_BUILD_ESKF15_ENABLED=(\w+)\s*\\?\s*$",
                             source_graph, re.MULTILINE)
    if len(eskf_values) > 1:
        raise ValueError("duplicate ESKF15 definition in source graph")
    if eskf_values:
        command.append(f"-DSYSTEM_BUILD_ESKF15_ENABLED={eskf_values[0]}")
    command += ["-I" + str(path) for path in logger_includes]
    command += [str(path) for path in logger_sources] + ["-lm", "-o", str(writer)]
    writer_command = list(command)
    subprocess.run(command, check=True, cwd=project, env=environment)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|DONE|3|4|logger-compile", flush=True)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|BEGIN|4|4|logger-integrity", flush=True)
    subprocess.run([str(writer), str(output / "persistent-objects.sslog"),
                    "persistent-objects"], check=True, cwd=project,
                   env=environment)
    decoders = list(project.glob("*.ssdecoder"))
    if len(decoders) != 1:
        raise ValueError("exactly one generated decoder is required for writer acceptance")
    for mode in ("normal", "overflow", "startup-overflow", "startup-burst", "startup-burst-overload"):
        writer_log = output / f"logger-{mode}.sslog"
        command = [str(writer), str(writer_log)] + ([mode] if mode != "normal" else [])
        subprocess.run(command, check=True, cwd=project, env=environment)
        command = [sys.executable, str(auditor), str(writer_log), "--decoder", str(decoders[0])]
        if mode in ("overflow", "startup-overflow", "startup-burst-overload"):
            command += ["--allow-queue-drops"]
        audited = subprocess.run(command, cwd=project, env=environment, text=True, capture_output=True)
        print(audited.stdout, end="", flush=True)
        print(audited.stderr, end="", file=sys.stderr, flush=True)
        audited.check_returncode()
        if eskf_values == ["1U"] and mode == "startup-burst":
            counts = json.loads(audited.stdout)["record_counts"]
            expected = {"ESKF15_BODY_INPUT": 19400, "ESKF15_MEASUREMENT": 38800,
                        "ESKF15_INITIAL_STATE": 1, "ESKF15_INITIAL_P_PART": 4}
            for name, count in expected.items():
                if counts.get(name, 0) != count:
                    raise ValueError(f"ESKF storage load omitted {name}: {counts.get(name, 0)} != {count}")
            project_data = json.loads((project / "SilverStar.ssproject").read_text(encoding="utf-8"))
            streams = project_data["logging"]["streams"]
            full_p = next(stream for stream in streams if stream["record"] == "FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART")
            if full_p["enabled"] and (counts.get("ESKF15_FULL_P_PART", 0) == 0 or counts["ESKF15_FULL_P_PART"] % 4):
                raise ValueError("Enabled ESKF full covariance must persist whole four-part snapshots")
    for diagnostic in (False, True):
        if diagnostic:
            writer = output / "logger_preflight_diagnostic.exe"
            command = writer_command[:-1] + [str(writer)]
            command[1:1] = ["-DSYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE=1U",
                            "-DSYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE=1U"]
            subprocess.run(command, check=True, cwd=project, env=environment)
        for seconds in (30, 120):
            name = f"preflight-{'diagnostic' if diagnostic else 'normal'}-{seconds}"
            writer_log = output / f"{name}.sslog"
            subprocess.run([str(writer), str(writer_log), "sparse", str(seconds)],
                           check=True, cwd=project, env=environment)
            subprocess.run([sys.executable, str(auditor), str(writer_log),
                            "--decoder", str(decoders[0])],
                           check=True, cwd=project, env=environment)
    print("FCCG_PROGRESS|STORAGE_INTEGRITY|DONE|4|4|logger-integrity", flush=True)
    return log


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    StorageIntegrity_Run(args.project.resolve(), args.compiler)
