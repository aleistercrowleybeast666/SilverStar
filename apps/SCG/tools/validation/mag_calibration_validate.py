"""Standalone, bounded Host validation of the owning magnetometer calibration unit.

No pytest/Qt, generated firmware tree, device access, downloads or cleanup.
Only the listed unit, test and headers are snapshotted into a new task directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCG = Path(__file__).resolve().parents[2]
ROOT = SCG.parents[1]
BUILTIN = SCG / "plugins/builtin"
CORE = BUILTIN / "silverstar_core_0_1_0/payload"
FIXTURE = CORE / "Tests/Host/mag_calibration"
CASES = (
    "absent_clear", "absent_save", "absent_status", "absent_complete",
    "absent_fault", "absent_inputs", "provider_disabled", "provider_wrong_class",
    "provider_wrong_instance", "provider_zero_identity", "provider_raw_only",
    "provider_unsupported", "provider_timeout", "provider_not_present",
    "wrong_packet", "wrong_sample", "wrong_sample_descriptor",
    "wrong_sample_instance", "sample_atomic", "normal", "save_failure",
    "stored_clear", "capability_loss", "changed_identity",
    "double_correction", "replacement_failure",
)
WARNINGS = (
    "-std=c11", "-O1", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
    "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wundef", "-Wformat=2",
    "-Wdouble-promotion", "-Wcast-align", "-Wcast-qual", "-Wstrict-prototypes",
    "-Wmissing-prototypes", "-Wswitch-enum", "-Wvla",
)
TF_CASES = ("tf_replacement", "tf_torn", "tf_crc", "tf_verify",
            "tf_config", "tf_sensor", "tf_endpoint", "tf_driver", "tf_model",
            "tf_legacy", "tf_no_card", "tf_before_save", "tf_clear_failure",
            "tf_corrupt", "tf_envelope", "tf_pending_identity", "tf_boot_load",
            "tf_selected_read_io", "tf_selected_read_crc", "tf_selected_read_missing",
            "tf_load_fault_contract", "tf_completion_contract")


def Digest_Get(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Command_Run(command: list[str], output: Path, records: list[dict]) -> int:
    try:
        result = subprocess.run(command, cwd=output, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
        record = dict(command=command, exit_code=result.returncode,
                      stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        record = dict(command=command, exit_code=None, error=str(error))
    records.append(record)
    return record["exit_code"] if record["exit_code"] is not None else 125


def Main_Run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory under .work/dev013_mag_calibration_*")
    parser.add_argument("--supplemental", action="store_true",
                        help="Also execute GCC analyzer and ARM unit compilation/link")
    parser.add_argument("--tf", action="store_true",
                        help="Link real persistence codec/service with bounded slot fault injection")
    parser.add_argument("--serial", action="store_true",
                        help="Also exercise no-logging SerialTask with synthetic RTOS/console ports")
    args = parser.parse_args()
    if args.serial and not args.tf:
        parser.error("--serial requires --tf")
    output = args.output.resolve()
    relative = output.relative_to((ROOT / ".work").resolve())
    if not relative.parts or not relative.parts[0].startswith(("dev013_mag_calibration_", "dev013_mag_tf_")):
        parser.error("Output must be in a versioned magnetometer task directory")
    if output.exists():
        parser.error("Output must be new; previous evidence is never overwritten")
    gcc = shutil.which("gcc")
    if gcc is None:
        parser.error("Host GCC unavailable; dependencies will not be downloaded")
    output.mkdir(parents=True)
    snapshot = output / "source"
    snapshot.mkdir()
    sources = (
        CORE / "System/Calibration/Src/system_mag_calibration.c",
        CORE / "System/Calibration/Inc/system_mag_calibration.h",
        CORE / "Interfaces/Inc/system_magnetometer_if.h",
        CORE / "Interfaces/Inc/system_device_types.h",
        CORE / "Interfaces/Inc/system_descriptor_if.h",
        CORE / "Interfaces/Inc/system_installation_calibration_if.h",
        CORE / "Common/Inc/silverstar_assert.h",
        CORE / "Common/Inc/silverstar_compiler.h",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc/platform_critical.h",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc/platform_memory.h",
        FIXTURE / "project_device_instances.h",
        FIXTURE / "test_system_mag_calibration.c",
        Path(__file__).resolve(),
    )
    production_units = ["system_mag_calibration.c"]
    if args.tf:
        storage = BUILTIN / "silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter"
        sources += (FIXTURE / "test_mag_tf.h", CORE / "Interfaces/Inc/system_storage_if.h",
                    CORE / "Interfaces/Inc/system_mag_calibration_storage_if.h",
                    storage / "Inc/persistent_storage.h",
                    storage / "Src/persistent_storage.c", storage / "Src/mag_calibration_storage.c")
        production_units += ["persistent_storage.c", "mag_calibration_storage.c"]
    cases = CASES + TF_CASES if args.tf else CASES
    if args.serial:
        sources += (CORE / "APP/Src/serial_task.c", CORE / "APP/Inc/serial_task.h")
        production_units += ["serial_task.c"]
        cases += ("tf_serial",)
    source_inventory = []
    for source in sources:
        destination = snapshot / source.name
        shutil.copyfile(source, destination)
        source_inventory.append(dict(path=str(source.relative_to(ROOT)),
                                     sha256=Digest_Get(source),
                                     snapshot=str(destination.relative_to(output))))
    if args.serial:
        ports = {
            "FreeRTOS.h": '#include <stdint.h>\ntypedef uint32_t TickType_t;\n#define pdMS_TO_TICKS(ms_) ((TickType_t)(ms_))\n',
            "task.h": '#include "FreeRTOS.h"\nvoid vTaskDelay(TickType_t ticks);\n',
            "system_user_config.h": '#define SILVERSTAR_PROTOCOL_LOGGING_ENABLED 0U\n',
            "system_console.h": 'void SystemConsole_Process(void);\n',
            "system_console_if.h": 'void SystemConsoleDevice_Process(void);\n',
        }
        # Test-only ports do not replace headers in any generated firmware.
        ports["FreeRTOS.h"] = '#ifndef __FREERTOS_H\n#define __FREERTOS_H\n' + ports["FreeRTOS.h"] + '#endif\n'
        for name, contents in ports.items():
            (snapshot / name).write_text(contents, encoding="utf-8")
    records: list[dict] = []
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    report = dict(owner=relative.parts[0],
                  purpose="Isolated calibration unit red/green, not firmware acceptance",
                  utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                  platform=platform.platform(), source_commit=commit.stdout.strip(),
                  sources=source_inventory, commands=records, cases=[],
                  critical_contract_review="NOT_PROVEN",
                  generated_power10="NOT_RUN: no full generated project in this batch",
                  full_firmware_host="NOT_RUN: shared entry/fixtures outside assigned scope",
                  full_firmware_arm="NOT_RUN: optional ARM result is a unit link only",
                  hardware="NOT_RUN: no hardware operations authorized")
    Command_Run([gcc, "--version"], output, records)
    executable = output / "mag_calibration_host.exe"
    definitions = ["-DSILVERSTAR_MAG_TF_TEST=1"] if args.tf else []
    if args.serial:
        definitions += ["-DSILVERSTAR_MAG_TF_SERIAL=1"]
    command = [gcc, *WARNINGS, *definitions, "-I", str(snapshot),
               *[str(snapshot / unit) for unit in production_units],
               str(snapshot / "test_system_mag_calibration.c"), "-lm", "-o", str(executable)]
    compile_code = Command_Run(command, output, records)
    report["host_compile_exit"] = compile_code
    if compile_code == 0:
        for case in cases:
            code = Command_Run([str(executable), case], output, records)
            report["cases"].append(dict(case=case, exit_code=code))
    supplemental_failed = False
    if args.supplemental:
        analyzer_codes = [Command_Run([gcc, *WARNINGS, "-fanalyzer", "-I", str(snapshot),
            "-c", str(snapshot / unit), "-o", str(output / (unit + ".analyzer.o"))],
            output, records) for unit in production_units]
        report["gcc_analyzer_exit"] = max(analyzer_codes)
        supplemental_failed = any(code != 0 for code in analyzer_codes)
        arm = shutil.which("arm-none-eabi-gcc")
        if arm is None:
            report["arm_unit_link"] = "UNAVAILABLE"
            supplemental_failed = True
        else:
            Command_Run([arm, "--version"], output, records)
            arm_code = Command_Run([arm, *WARNINGS, *definitions, "-mcpu=cortex-m4", "-mthumb",
                "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard", "-fstack-usage",
                "-DSILVERSTAR_MAG_CAL_ARM_LINK_ONLY=1",
                "-I", str(snapshot), *[str(snapshot / unit) for unit in production_units],
                str(snapshot / "test_system_mag_calibration.c"),
                "-nostartfiles", "-Wl,-e,main", "-Wl,--fatal-warnings",
                "-Wl,-Map=" + str(output / "mag_calibration_arm.map"),
                "-lm", "-o", str(output / "mag_calibration_arm.elf")], output, records)
            report["arm_unit_compile_link_exit"] = arm_code
            supplemental_failed = supplemental_failed or arm_code != 0
    report["live_sources_unchanged"] = all(
        Digest_Get(ROOT / item["path"]) == item["sha256"] for item in source_inventory)
    passed = sum(item["exit_code"] == 0 for item in report["cases"])
    report["passed"] = passed
    report["failed"] = len(report["cases"]) - passed
    complete = (compile_code == 0 and passed == len(cases) and
                not supplemental_failed and report["live_sources_unchanged"])
    report["exit_code"] = 0 if complete else 1
    report_path = output / "results.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    inventory = [dict(path=str(path.relative_to(output)), sha256=Digest_Get(path),
                      bytes=path.stat().st_size, owner=report["owner"],
                      purpose="retained test evidence; no automatic cleanup")
                 for path in sorted(output.rglob("*")) if path.is_file()]
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n",
                                           encoding="utf-8")
    print(f"HOST cases={len(report['cases'])} passed={passed} failed={report['failed']} compile_exit={compile_code}")
    for item in report["cases"]:
        if item["exit_code"] != 0:
            print(f"FAIL {item['case']} exit={item['exit_code']}")
    if args.supplemental:
        print(f"ANALYZER exit={report.get('gcc_analyzer_exit')} ARM_UNIT_LINK exit={report.get('arm_unit_compile_link_exit', 'unavailable')}")
    print("CRITICAL_CONTRACT_REVIEW NOT_PROVEN; full generated gates and hardware not run")
    print(f"Evidence: {report_path}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(Main_Run())
