from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


@pytest.fixture(scope="module")
def runtime_project(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path_factory.mktemp("runtime")
    service = FccgService(root)
    model = service.ReferenceProject_Create("RuntimeRegression")
    service.Project_Save(model, project, confirm_dangerous=True)
    return project, SourceGraph_Resolve(model, service.catalog)


def _Host_Run(project, sources, defines=(), *, reject=False):
    root, graph = project
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    output = root / "build/FCCG/Host/Tests/runtime-regression.exe"
    output.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(TEMP=str(output.parent), TMP=str(output.parent))
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(root / "Tests/Host"),
               "-include", str(root / "Generated/Inc/project_flight_config.h")]
    legacy = "Protocol/Src/air_protocol.c" in sources
    if legacy:
        # These cases intentionally assert historical AIR byte positions and
        # command-manager behavior. Compile the retained codec as a Host fixture;
        # it is not admitted as a normal generated Flight protocol selection.
        owner = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_protocol_telemetry_air_m0/payload'
        fixture = output.parent / 'legacy-wire'; fixture.mkdir(exist_ok=True)
        (fixture / 'project_telemetry_protocol.h').write_text(
            '#ifndef __PROJECT_TELEMETRY_PROTOCOL_H\n#define __PROJECT_TELEMETRY_PROTOCOL_H\n'
            '#include "air_protocol.h"\ntypedef uint8_t TelemetrySequence;\n'
            '#include "telemetry_extended_if.h"\n#endif\n', encoding='utf-8')
        command += ['-I' + str(fixture), '-I' + str(owner / 'Protocol/Inc'), '-DSYSTEM_TELEMETRY_TM_ENABLED=0U']
    command += ["-D" + value for value in defines]
    command += ["-I" + str(root / include) for include in graph.include_dirs]
    command += [str(owner / source) if legacy and source == 'Protocol/Src/air_protocol.c'
                else str(root / source) for source in sources]
    command += [str(root / "Common/Src/silverstar_assert.c"), "-lm", "-o", str(output)]
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True)
    if reject:
        assert result.returncode != 0
        assert "Calibration build procedure mask contains unknown bits" in result.stderr
        return
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(output)], cwd=root, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


CALIBRATION_SOURCES = [
    "System/Calibration/Src/system_calibration.c",
    "System/Calibration/Src/system_calibration_correction.c",
    "Algorithm/Calibration/Src/imu_six_face_calibration.c",
]


@pytest.mark.parametrize("mask", (0, 2, 4, 6))
def test_calibration_build_gate_and_wire_mask(runtime_project, mask):
    _Host_Run(runtime_project, ["Tests/Host/test_calibration_build_gate.c",
                               "Protocol/Src/air_protocol.c", *CALIBRATION_SOURCES],
              [f"SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK={mask}"])


@pytest.mark.parametrize("mask", (1, 8, 0x100))
def test_unknown_calibration_procedure_bits_reject_compile(runtime_project, mask):
    _Host_Run(runtime_project, ["Tests/Host/test_calibration_build_gate.c",
                               "Protocol/Src/air_protocol.c", *CALIBRATION_SOURCES],
              [f"SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK={mask}"], reject=True)


@pytest.mark.parametrize("source", ("test_runtime_startup.c", "test_fault_hook.c"))
def test_production_app_startup_indicator_identity_and_fault_context(runtime_project, source):
    _Host_Run(runtime_project, [
        "Tests/Host/" + source, "APP/Src/app_tasks.c",
        "System/Indicator/Src/system_indicator.c",
        "FlightLogic/Indicator/GpioStatus/Src/indicator_service.c",
        *CALIBRATION_SOURCES,
    ])


def test_real_telemetry_task_defers_alignment_and_gates_calibration(runtime_project):
    _Host_Run(runtime_project, [
        "Tests/Host/test_runtime_commands.c", "APP/Src/telemetry_task.c",
        "Common/Src/common_format.c",
        "Modules/Src/telemetry_service.c", "Protocol/Src/air_protocol.c",
        "System/Alignment/Src/system_alignment.c",
        "System/Alignment/Src/system_alignment_source.c", *CALIBRATION_SOURCES,
    ], ["SILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U"])


def test_runtime_sources_survive_reference_import(monkeypatch, workspace_root):
    import tools.import_reference_components as importer

    monkeypatch.setattr(importer, "_ManifestValues_Get", lambda *_: [])
    components = {item["manifest"]["id"]: item for item in importer._Components_Get(
        Path("unused"), {"commit": "fixture", "snapshot_digest": "fixture"})}
    core = components["silverstar.core.0_1_0"]
    for relative in (
        "APP/Inc/app_task_config.h", "APP/Src/app_tasks.c",
        "Common/Inc/silverstar_assert.h", "Common/Src/silverstar_assert.c",
        "System/Calibration/Inc/system_calibration.h",
        "System/Calibration/Src/system_calibration_correction.c",
        "System/Calibration/Src/system_calibration.c",
        "System/Alignment/Src/system_alignment.c",
        "Tests/Host/test_runtime_startup.c", "Tests/Host/test_calibration_build_gate.c",
        "Tests/Host/test_runtime_commands.c",
    ):
        assert relative in core["fccg_owned_files"]
        assert (workspace_root / core["fccg_owned_files"][relative]).is_file()
    assert "OS/FreeRTOS/freertos_hooks.c" in components[
        "silverstar.os.freertos_11_3_0"]["fccg_owned_files"]
    for relative in (
        "Tools/check_task_stacks.py", "Tools/stack_arm.py", "Tools/stack_runtime.py",
        "Tools/stack_review.py", "Tools/stack_manifest.py", "Tools/software_stack_inputs.json", "Tools/software_stack_review.md", "Tools/h743_stack_inputs.json",
        "APP/Inc/control_research.h", "APP/Src/control_research.c",
        "APP/Src/control_research_runtime.c", "Interfaces/Inc/system_navigation_provenance.h",
        "Tests/Host/test_control_research.c", "Tests/Host/test_control_provenance.c",
    ):
        expected = "plugins/builtin/silverstar_core_0_1_0/payload/" + relative
        assert core["fccg_owned_files"][relative] == expected
        assert (workspace_root / expected).is_file()
        assert relative not in core["overlay_files"]
        assert relative not in core["reference_files"]
        if relative.startswith("APP/Src/"):
            assert relative in core["manifest"]["build"]["sources"]
    import hashlib
    from silverstar_fccg.project.stack_manifest import Manifest_Load
    owner = workspace_root/'plugins/builtin/silverstar_core_0_1_0/payload'
    index = owner/'Tools/software_stack_inputs.json'
    review = Manifest_Load(owner, index, hashlib.sha256(index.read_bytes()).hexdigest())
    for relative in {*[row['path'] for row in review['sealed_case_files'].values()],
                     *[row['review_document'] for row in review['cases']]}:
        assert core['fccg_owned_files'][relative] == 'plugins/builtin/silverstar_core_0_1_0/payload/'+relative
        assert relative not in core['reference_files'] and relative not in core['overlay_files']
    mcu = components["silverstar.mcu.stm32f407vet6"]
    for relative in ("Platform/STM32F4/Src/platform_gpio_stm32f4.c", "STM32F407XX_FLASH.ld"):
        assert (workspace_root / mcu["fccg_owned_files"][relative]).is_file()
        assert relative not in mcu["overlay_files"]


def test_imported_documentation_replay_is_idempotent(tmp_path, workspace_root):
    from tools.import_reference_components import _ImportedDocumentation_Adapt
    from silverstar_fccg.core.workspace import WorkspacePolicy

    relative = Path("silverstar_protocol_logging_sslog_0_0/docs/STORAGE_AND_FLIGHT_LOG.md")
    destination = tmp_path / relative
    policy = WorkspacePolicy(tmp_path)
    policy.File_Copy(workspace_root / "plugins/builtin" / relative, destination)
    _ImportedDocumentation_Adapt(tmp_path, policy)
    first = destination.read_bytes()
    _ImportedDocumentation_Adapt(tmp_path, policy)
    assert destination.read_bytes() == first
    assert first.count("## CALIBRATION_RESULT 生效快照语义".encode()) == 1
    assert first.count("## FCCG独立协议插件归属".encode()) == 1


def test_runtime_generation_includes_stack_report(runtime_project, workspace_root):
    project, _ = runtime_project
    makefile = (project / "Makefile").read_text(encoding="utf-8")
    assert "-fstack-usage" in makefile
    assert "stack-report: all" in makefile
    for name in ("check_task_stacks.py", "stack_arm.py", "stack_runtime.py",
                 "stack_review.py", "stack_manifest.py", "software_stack_inputs.json", "software_stack_review.md", "h743_stack_inputs.json"):
        assert (project / "Tools" / name).read_bytes() == (
            workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/Tools" / name).read_bytes()
    import hashlib
    from silverstar_fccg.project.stack_manifest import Manifest_Load
    index = project/'Tools/software_stack_inputs.json'
    review = Manifest_Load(project, index, hashlib.sha256(index.read_bytes()).hexdigest())
    for row in review['sealed_case_files'].values():
        assert (project/row['path']).read_bytes() == (
            workspace_root/'plugins/builtin/silverstar_core_0_1_0/payload'/row['path']).read_bytes()


@pytest.mark.parametrize("extra", ("all: stack-report\n", "all:\n\tpython generate.py\n"))
def test_architecture_rejects_build_time_generators(runtime_project, extra):
    project, _ = runtime_project
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None or shutil.which("mingw32-make") is None:
        pytest.skip("PowerShell and Make are needed for the real architecture gate")
    makefile = project / "Makefile"
    original = makefile.read_text(encoding="utf-8")
    command = [shell, "-NoProfile", "-File", "Tools/check_architecture.ps1"]
    try:
        makefile.write_text(original + "\n" + extra, encoding="utf-8")
        result = subprocess.run(command, cwd=project, capture_output=True, text=True)
        assert result.returncode != 0
        assert "Build manifest invokes a generator or depends on the offline stack report" in result.stdout
    finally:
        makefile.write_text(original, encoding="utf-8")
