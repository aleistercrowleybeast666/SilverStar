"""Real selected Host CAL/INS/origin/START chain; bounded bus/storage inputs.

The recorded baseline uses the same fixture and ONE_FACE configuration.
Target ARM and hardware qualification are separate evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.generator.render import _DeviceBuildCapabilitiesHeader_Render, _FlightConfigHeader_Render

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures/mpu_epoch"
CORE = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload"
BASELINE = ROOT / ".work/f103_irq_checkpoint/ret6"
CURRENT = ROOT / ".work/sf6_epoch_v1/ret6"


def compile_flow(directory, *, baseline=False, cal_none=False, draft_source=None):
    service = FccgService(ROOT / "apps/SCG")
    model = ProjectModel_Load(BASELINE / "SilverStar.ssproject")
    # Only this independent Host fixture chooses ONE_FACE. Saved production
    # configurations and the target resource-comparison configuration stay NONE.
    model.modes["calibration"] = [] if cal_none else ["OneFace"]
    catalog = service.catalog.ProjectView_Get(model)
    owner_paths = {}
    owner_includes = []
    for component in model.ComponentIds_Get():
        manifest = catalog.Component_Get(component)
        for source in manifest.build.sources:
            owner_paths[source] = manifest.payload_root / source
        owner_includes.extend(manifest.payload_root / path for path in manifest.build.include_dirs)
    project = BASELINE if baseline else CURRENT
    runner = (CORE / "Tests/Host/run_tests.ps1").read_text(encoding="utf8")
    def paths(block):
        return re.findall(r'"\$repoRoot\\([^"\n]+)"', block)
    preparation = re.search(r'\$preparationSources = @\((.*?)\n\)', runner, re.S)[1]
    optional = re.search(r'\$optionalStartSources = .*?\+ @\((.*?)\n\) \+ \$sslogSources', runner, re.S)[1]
    selected = [name.replace("\\", "/") for name in paths(preparation) + paths(optional)]
    selected = [name for name in selected if not name.endswith(("test_estimator_preparation.c", "ins_task.c",
        "test_optional_gnss_start.c", "optional_start_ins_inputs.c", "optional_start_mag_inputs.c",
        "flight_task.c", "system_source_selector.c"))]
    selected += ["Protocol/SSLOG/Src/sslog_protocol.c", "Protocol/SSLOG/Src/sslog_records.c",
        "Algorithm/Estimator/SF6/Src/navigation_sf6.c", "Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c",
        "System/Inertial/Src/system_inertial.c", "System/User/system_user_inertial_config.c",
        "Generated/Src/project_device_instances.c",
        "Devices/SensorBus/Src/sensor_imu.c", "Devices/SensorBus/Src/sensor_register_bus.c",
        "Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c", "Devices/IMU/MPU6050/Src/mpu6050_device.c",
        "Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c", "Common/Src/silverstar_assert.c"]
    graph = (project / "Generated/project_sources.mk").read_text(encoding="utf8")
    if "APP/Src/logger_bus_minimal.c" in graph:
        selected = [name.replace("APP/Src/logger_bus.c", "APP/Src/logger_bus_minimal.c") for name in selected]
    selected += re.findall(r'^\s+(Algorithm/Alignment/[\w/]+\.c)', graph, re.M)
    if not baseline:
        selected += ["System/Src/system_imu_epoch.c"]
    selected = list(dict.fromkeys(selected))
    def owner_file(name):
        if name in owner_paths:
            return owner_paths[name]
        # Some real Host support modules are excluded from a feature tier's
        # target graph. Resolve their explicit owning payload, never a stub.
        candidates = [catalog.Component_Get(component).payload_root / name for component in model.ComponentIds_Get()]
        candidates = [path for path in candidates if path.is_file()]
        assert len(candidates) == 1, (name, candidates)
        return candidates[0]
    sources = [project / name if baseline or name.startswith(("Generated/", "Tests/Host/"))
               else owner_file(name) for name in selected]
    if draft_source is not None:
        sources = [draft_source / path.relative_to(ROOT) if
                   (draft_source / path.relative_to(ROOT)).is_file() else path for path in sources]
    sources += list(FIXTURE.glob("*.c"))
    # Keep the actual IMU selector and its private state; other device inputs
    # remain the established Host projections. Rename only unrelated exports
    # in a test wrapper, not production selector code or IMU operations.
    selector = project / "System/Src/system_source_selector.c" if baseline else CORE / "System/Src/system_source_selector.c"
    text = selector.read_text(encoding="utf8")
    names = sorted(set(re.findall(r'^.*?\b(System(?:Gnss|Barometer|Magnetometer|HardwareQuaternion|Telemetry|ConsoleDevice)_\w+)\s*\(', text, re.M)))
    wrapper = directory / "selector_inputs.c"
    wrapper.write_text("\n".join("#define " + name + " Test_Unused_" + name for name in names) +
        '\n#include "' + selector.as_posix() + '"\n', encoding="utf8")
    sources.append(wrapper)
    # Original existing Host projections include their own task translation
    # units via relative paths. Keep those input helpers with recorded project.
    for index, name in enumerate(selected):
        if name.startswith("Tests/Host/optional_start_"):
            sources[index] = project / name
    (directory / "project_flight_config.h").write_text(_FlightConfigHeader_Render(model, catalog), encoding="utf8")
    capabilities = _DeviceBuildCapabilitiesHeader_Render(model, catalog)
    if baseline:
        capabilities = capabilities.replace("#define SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED 1U",
                                              "#define SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED 0U")
    (directory / "project_device_build_capabilities.h").write_text(capabilities, encoding="utf8")
    # Use the existing bounded MPU resource fixture instead of ARM board access.
    includes = [directory, Path(__file__).parent / "fixtures/mpu_recovery", FIXTURE,
        CORE / "Tests/Host", project / "Tests/Host", project / "Generated/Inc"]
    if not baseline:
        includes += owner_includes + [CORE / "APP/Src"]
    if draft_source is not None:
        includes = [draft_source / path.relative_to(ROOT) for path in owner_includes
                    if (draft_source / path.relative_to(ROOT)).is_dir()] + includes
    include_block = re.search(r'C_INCLUDES \+= \\\n(.*?)(?:\n\n|\Z)', graph, re.S)[1]
    includes += [project / line.strip().removesuffix("\\").strip() for line in include_block.splitlines()]
    includes += [project / "APP/Src", project / "Devices/Storage/SdSdioFatFs/Adapter/Inc"]
    definitions = re.findall(r'^\s+(SYSTEM_(?:ALIGNMENT_BUILD|BUILD_(?:ESTIMATOR|FUSION|SF6|MECHANIZATION))[\w]*=[\w]+)', graph, re.M)
    binary = directory / "epoch_start.exe"
    argv = [os.environ.get("HOST_GCC", "D:/msys64/ucrt64/bin/gcc.exe"), "-std=c11", "-O2", "-flto=2",
        "-Wall", "-Wextra", "-Werror", "-pedantic", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
        "-include", str(directory / "project_flight_config.h")]
    # This fixture's raw acceleration and axis map expose stationary +Z.
    # The saved production CAL_NONE project retains its existing default.
    argv += ["-DSYSTEM_IMU_STARTUP_GRAVITY_DIRECTION=SYSTEM_AXIS_DIRECTION_Z_POSITIVE"]
    if cal_none:
        argv += ["-DTEST_CAL_NONE=1"]
    if draft_source is not None:
        argv += ["-DTEST_EPOCH_DRAFT=1"]
    argv += ["-D" + value for value in definitions] + ["-I" + str(path) for path in includes]
    argv += [str(path) for path in sources] + ["-lm", "-o", str(binary)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    (directory / "compile.json").write_text(json.dumps({"argv": argv, "exit": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "baseline": baseline, "fixture_calibration": model.modes,
        "sources": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sources]}, indent=2), encoding="utf8")
    assert result.returncode == 0, result.stderr
    return binary


def run_cases(directory, binary, cases):
    rows = []
    for case in cases:
        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=30)
        rows.append({"case": case, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    (directory / "cases.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
    return rows


def test_recorded_baseline_normal_start_and_recovery_failure(tmp_path):
    binary = compile_flow(tmp_path, baseline=True)
    rows = run_cases(tmp_path, binary, [1, 2, 13])
    assert rows[0]["exit"] == 0, rows
    assert rows[1]["exit"] != 0 and rows[2]["exit"] != 0, rows


def test_current_requalification_and_start_fault_boundaries(tmp_path):
    binary = compile_flow(tmp_path)
    rows = run_cases(tmp_path, binary, [1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 20, 21, 30, 40])
    assert all(row["exit"] == 0 for row in rows), rows


def test_none_initial_start_and_recovery_stays_unqualified(tmp_path):
    binary = compile_flow(tmp_path, cal_none=True)
    rows = run_cases(tmp_path, binary, [1, 2])
    assert all(row["exit"] == 0 for row in rows), rows


def test_recorded_epoch_draft_clipped_quality_failure(tmp_path):
    archive = ROOT / '.work/evidence/sf6_epoch_v1/SF6_MPU_epoch_draft_checkpoint.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'a47904362a55d2d7dcb604394ce6270452c39f5c4030e30a698289bb16a0c37c'
    # A bounded short fixture path avoids Windows MAX_PATH without changing
    # machine policy or creating a repository copy.
    draft = ROOT / '.work/ed_a479'
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read('CHECKPOINT.json'))['source_manifest']
        for item in manifest:
            name = item['archive_path']
            if not name.startswith('source/apps/SCG/plugins/builtin/'):
                continue
            payload = bundle.read(name)
            assert hashlib.sha256(payload).hexdigest() == item['sha256']
            target = draft / name.removeprefix('source/')
            target.resolve().relative_to(draft.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']
            else:
                target.write_bytes(payload)
    binary = compile_flow(tmp_path, draft_source=draft)
    rows = run_cases(tmp_path, binary, [1, 40])
    assert rows[0]['exit'] == 0, rows
    assert rows[1]['exit'] != 0, rows
    assert 'ImuSampleBus_Pop(&sample) == IMU_SAMPLE_BUS_RESULT_OK' in rows[1]['stderr'], rows
