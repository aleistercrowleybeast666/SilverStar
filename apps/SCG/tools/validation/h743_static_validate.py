"""Generate and check isolated H743ZI candidates; never flash or access hardware."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SCG = Path(__file__).resolve().parents[2]
REPOSITORY = SCG.parents[1]
sys.path.insert(0, str(SCG / "src"))

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.validation import Project_Validate


def Json_Write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def CubeMxStaticInput_Create(source: Path, destination: Path) -> Path:
    """Create a private generated-input derivative; never rewrite CubeMX input.

    CubeMX 6.15 emits unused heap aliases even for LFN mode 2. Remove exactly
    that alias block only for stack LFN, no exFAT and two static file-lock slots.
    Do not remove allocator calls, change the generic importer, or relax gates.
    Preserve the generated project's driver subset for importer completeness;
    the full vendor SDK is never copied and compiled drivers remain plugin-owned.
    """
    if destination.exists():
        raise ValueError("Static input destination must not already exist")
    source = source.resolve(strict=True)
    config = source / "FATFS/Target/ffconf.h"
    if any(path.is_symlink() for path in (config, config.parent, config.parent.parent)):
        raise ValueError("Static CubeMX configuration must not be linked")
    original = config.read_text(encoding="utf8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", original, flags=re.DOTALL)
    for macro, expected in (("_USE_LFN", "2"), ("_FS_EXFAT", "0"), ("_FS_LOCK", "2"), ("_FS_REENTRANT", "0")):
        values = [value.strip() for value in re.findall(
            r"(?m)^[ \t]*#[ \t]*define[ \t]+" + macro + r"[ \t]+([^\n]+)", code)]
        if values != [expected]:
            raise ValueError("Unsupported static FatFs configuration: " + macro)
    block = re.compile(r"/\* define the ff_malloc ff_free macros as standard malloc free \*/\n"
                       r"#if !defined\(ff_malloc\) && !defined\(ff_free\)\n#include <stdlib.h>\n"
                       r"#define ff_malloc[ \t]+malloc\n#define ff_free[ \t]+free\n#endif")
    prepared, count = block.subn("/* Static candidate: stack LFN only; heap aliases deliberately absent. */", original)
    if count != 1 or re.search(r"\b(?:ff_malloc|ff_free|malloc|calloc|realloc|free)\b",
                              re.sub(r"/\*.*?\*/", "", prepared, flags=re.DOTALL)):
        raise ValueError("Unreviewed FatFs allocation-hook block; input left unchanged")
    paths = [path for name in ("Core", "FATFS", "Drivers") for path in (source / name).rglob("*") if path.is_file()]
    paths += [path for path in source.iterdir() if path.is_file() and
              (path.suffix in (".ioc", ".s", ".ld") or path.name in ("Makefile", ".mxproject"))]
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Static CubeMX input must not contain linked files")
    destination.mkdir(parents=True)
    inventory = {}
    for path in paths:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        inventory[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    target = destination / "FATFS/Target/ffconf.h"
    target.write_text(prepared, encoding="utf8")
    Json_Write(destination.parent / "static-input-receipt.json", {
        "schema": "silverstar.static-cubemx-derivative/1", "input_files_sha256": inventory,
        "changes": [{"path": "FATFS/Target/ffconf.h", "operation": "remove_exact_unused_heap_alias_block",
                     "preconditions": "LFN=2 EXFAT=0 LOCK=2 (static FILESEM array) REENTRANT=0",
                     "before_sha256": inventory["FATFS/Target/ffconf.h"],
                     "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
        "hardware_tested": False,
    })
    return destination


def Scenario_Create(service, cube: Path, algorithm: str, imu_count: int, tools: dict):
    model = service.ProjectDraft_Create(f"H743ZI_{algorithm}_x{imu_count}")
    model.mcu = "silverstar.mcu.stm32h743zit6"
    model.mcu_family = "silverstar.mcu_family.stm32h7"
    model.os = "silverstar.os.freertos_11_3_0_cm7"
    model.board = ""
    model.build = replace(model.build, target_profile="SilverStar_H743ZI",
                          memory_layout="legacy", tool_paths=tools)
    model.device_instances = [DeviceInstance(f"imu{i}", "silverstar.device.imu.bmi088")
                              for i in range(imu_count)] + [
        DeviceInstance("gnss0", "silverstar.device.gnss.neo_m9n"),
        DeviceInstance("barometer0", "silverstar.device.barometer.bmp390"),
        DeviceInstance("magnetometer0", "silverstar.device.magnetometer.mmc5983ma"),
        DeviceInstance("telemetry0", "silverstar.device.telemetry.sx1281",
                       module_variant="e28_2g4m27sx", tx_power_dbm=27),
        DeviceInstance("maintenance0", "silverstar.device.console.uart"),
        DeviceInstance("storage0", "silverstar.device.storage.sdmmc_fatfs_h7"),
        # Existing START source uses a test GPIO. No ignition load is connected.
        DeviceInstance("launch_ignition0", "silverstar.device.actuator.launch_ignition"),
    ]
    model.ground_target = replace(model.ground_target, enabled=False)
    model.strategies["estimator"] = "silverstar.algorithm.estimator." + algorithm
    model.strategies["alignment"] = "silverstar.algorithm.alignment.gravity_known_yaw"
    model.strategies["landing"] = None
    model.modes = {key: [] for key in model.modes}
    model.resource_assignments = {}
    model.capability_source_overrides = {}
    model.hardware = service.CubeMxProject_Import(cube, model, risk_acknowledged=True).hardware
    model.resource_assignments = {
        "gnss0:data": "USART1", "gnss0:reset": "GNSS_RESET", "gnss0:timepulse": "GNSS_PPS",
        "gnss0:time": "SYSTEM_TIME", "telemetry0:radio_bus": "SPI1", "telemetry0:radio_nss": "RADIO_NSS",
        "telemetry0:radio_reset": "RADIO_RESET", "telemetry0:radio_busy": "RADIO_BUSY",
        "telemetry0:radio_dio1": "RADIO_DIO1", "telemetry0:radio_rx_en": "RADIO_RX_EN",
        "telemetry0:radio_tx_en": "RADIO_TX_EN", "telemetry0:time": "SYSTEM_TIME",
        "maintenance0:console": "USART2", "storage0:storage": "SDMMC1", "storage0:time": "SYSTEM_TIME",
        "launch_ignition0:output": "STATUS_LED", "barometer0:data": "I2C1",
        "barometer0:time": "SYSTEM_TIME", "magnetometer0:data": "I2C1", "magnetometer0:time": "SYSTEM_TIME",
    }
    for index in range(imu_count):
        for role in ("data", "gyro"):
            model.resource_assignments[f"imu{index}:{role}"] = f"I2C{index + 1}"
        model.resource_assignments[f"imu{index}:time"] = "SYSTEM_TIME"
    model = service.ProjectConfiguration_Reconcile(model).model
    # Exercise the existing model's software-only gate. These are explicit
    # static-test assumptions, not measured priors, lever arms or time bounds.
    parameters = model.algorithm_parameters[model.strategies["estimator"]]
    for key in parameters:
        if key in ("software_validation_build", "initialization_confirmed", "gnss_imu_colocated_confirmed"):
            parameters[key] = 1
        elif key == "gravity_mps2":
            parameters[key] = 9.80665
        elif key in ("position_nis_gate", "velocity_nis_gate", "magnetic_nis_gate"):
            parameters[key] = 16.27
        elif key.startswith("gyro_density_"):
            parameters[key] = 0.002
        elif key.startswith("accel_density_"):
            parameters[key] = 0.03
        elif key.startswith("gyro_bias_rw_density_"):
            parameters[key] = 0.0001
        elif key.startswith("accel_bias_rw_density_"):
            parameters[key] = 0.001
        elif key.startswith("initial_variance_"):
            parameters[key] = 1.0
        elif key == "installation_q_0":
            parameters[key] = 1.0
        elif key == "magnetic_reference_ut":
            parameters[key] = 45.0
        elif key == "magnetic_min_norm_ratio":
            parameters[key] = 0.7
        elif key == "magnetic_max_norm_ratio":
            parameters[key] = 1.3
        elif key == "inclination_rad":
            parameters[key] = 0.8
    return model, Project_Validate(model, service.catalog)


def Command_Run(command: list[str], destination: Path, environment: dict) -> dict:
    with destination.open("w", encoding="utf8") as log:
        result = subprocess.run(command, cwd=REPOSITORY, env=environment,
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    return {"command": command, "exit_code": result.returncode,
            "log": destination.relative_to(REPOSITORY).as_posix()}


def Candidate_Check(flight: Path, arguments, environment: dict) -> dict:
    evidence = {}
    gcc_directory = arguments.arm_gcc.parent.as_posix()
    for target in ("all", "architecture-check", "power10-check", "static-analysis", "artifact-check", "stack-report"):
        command = [str(arguments.make), "-C", str(flight), f"-j{arguments.jobs}", "CONFIG=" + arguments.config,
                   "GCC_PATH=" + gcc_directory, target]
        evidence[target] = Command_Run(command, flight.parent / (target + ".log"), environment)
        print(f"{flight.parent.name}: {target} exit={evidence[target]['exit_code']}", flush=True)
    command = [sys.executable, str(flight / "Tools/check_task_stacks.py"), "--project", str(flight),
               "--config", arguments.config, "--prefix", gcc_directory + "/arm-none-eabi-", "--diagnostic"]
    evidence["stack-diagnostic"] = Command_Run(command, flight.parent / "stack-diagnostic.log", environment)
    # Freeze all generated inputs, excluding build outputs and mutable IDE caches.
    source_files = {}
    for name in ("Makefile", "SilverStar.ssproject", "STM32H743XX_FLASH.ld"):
        source_files[name] = hashlib.sha256((flight / name).read_bytes()).hexdigest()
    for path in sorted(flight.rglob("*")):
        relative = path.relative_to(flight)
        if path.is_file() and relative.parts[0] not in ("build", ".eide", ".vscode"):
            source_files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    Json_Write(flight.parent / "source-inventory.json", source_files)
    artifacts = {}
    for path in flight.glob("build/FCCG/SilverStar_H743ZI/**/*.elf"):
        artifacts[path.relative_to(flight).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    software_passed = all(evidence[name]["exit_code"] == 0 for name in
                          ("all", "architecture-check", "power10-check", "static-analysis", "artifact-check", "stack-report"))
    return {"gates": evidence, "artifacts": artifacts, "software_gates_passed": software_passed,
            "whole_program_stack_acceptance": "NOT PROVEN; diagnostic is not a gate pass",
            "hardware_tested": False, "flight_tested": False}


def Main_Run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cube-project", type=Path, required=True, help="Read-only CubeMX-generated fixture directory")
    parser.add_argument("--output", type=Path, required=True, help="New, nonexistent directory inside this repository's .work")
    parser.add_argument("--algorithms", nargs="+", choices=("eskf20", "inekf15", "inekf20"),
                        default=("eskf20", "inekf15", "inekf20"))
    parser.add_argument("--dual-imu", action="store_true", help="Also generate ESKF20 with two BMI088 instances, one selected primary")
    parser.add_argument("--run", action="store_true", help="Actually compile, analyze and run emitted checks; no hardware actions")
    parser.add_argument("--arm-gcc", type=Path, required=True)
    parser.add_argument("--make", type=Path, required=True)
    parser.add_argument("--host-gcc", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--config", choices=("Release", "Debug"), default="Release")
    arguments = parser.parse_args()
    if not 1 <= arguments.jobs <= 16:
        parser.error("jobs must be between 1 and 16")
    output = arguments.output.resolve()
    output.relative_to((REPOSITORY / ".work").resolve())
    if output == (REPOSITORY / ".work").resolve() or output.exists():
        parser.error("output must be a new task subdirectory; existing evidence is never overwritten")
    cube = arguments.cube_project.resolve(strict=True)
    if not cube.is_dir() or len(list(cube.glob("*.ioc"))) != 1:
        parser.error("cube-project must contain exactly one IOC and its generated sources")
    for name in ("arm_gcc", "make", "host_gcc"):
        executable = getattr(arguments, name).resolve(strict=True)
        if not executable.is_file():
            parser.error(name + " must be an executable file")
        setattr(arguments, name, executable)
    output.mkdir(parents=True)
    cube = CubeMxStaticInput_Create(cube, output / "CubeMX_StaticInput")
    service = FccgService(SCG)
    service.policy = WorkspacePolicy(REPOSITORY)
    tools = {"compiler": str(arguments.arm_gcc), "make": str(arguments.make), "host_gcc": str(arguments.host_gcc)}
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(arguments.make.parent),
                                          str(arguments.arm_gcc.parent), str(arguments.host_gcc.parent), environment["PATH"]])
    cases = [(algorithm, 1) for algorithm in dict.fromkeys(arguments.algorithms)]
    if arguments.dual_imu:
        cases.append(("eskf20", 2))
    report = {"schema": "silverstar.h743-static-validation/1", "configuration": arguments.config,
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip(),
              "test_allocation_only": True, "cases": {}}
    for algorithm, count in cases:
        label = f"{algorithm}_x{count}"
        model, validation = Scenario_Create(service, cube, algorithm, count, tools)
        issues = [{"level": item.level, "code": item.code, "message": item.message} for item in validation.issues]
        Json_Write(output / (label + "_validation.json"), {"valid": validation.valid, "issues": issues})
        if not validation.valid:
            report["cases"][label] = {"generated": False, "issues": issues}
            Json_Write(output / "summary.json", report)
            continue
        destination = output / label
        service.ProjectRoot_Save(model, destination)
        TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        report["cases"][label] = {"generated": True}
        if arguments.run:
            report["cases"][label].update(Candidate_Check(destination / "Flight_Controller", arguments, environment))
        Json_Write(output / "summary.json", report)
    # Exit status covers the executed software gates. Hardware qualification
    # and whole-program manual acceptance remain separate explicit fields.
    print(output / "summary.json", flush=True)
    passed = all(row["generated"] and (not arguments.run or row.get("software_gates_passed", False))
                 for row in report["cases"].values())
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(Main_Run())
