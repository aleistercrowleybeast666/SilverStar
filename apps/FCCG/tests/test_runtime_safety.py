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
    command += ["-D" + value for value in defines]
    command += ["-I" + str(root / include) for include in graph.include_dirs]
    command += [str(root / source) for source in sources]
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
    assert core["overlay_files"]["Tools/check_task_stacks.py"] == "check_task_stacks.py"


def test_imported_documentation_replay_is_idempotent(tmp_path, workspace_root):
    from tools.import_reference_components import _ImportedDocumentation_Adapt
    from silverstar_fccg.core.workspace import WorkspacePolicy

    relative = Path("silverstar_protocol_logging_sslog_0_0/docs/STORAGE_AND_FLIGHT_LOG.md")
    destination = tmp_path / relative
    policy = WorkspacePolicy(workspace_root)
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
    assert (project / "Tools/check_task_stacks.py").read_bytes() == (
        workspace_root / "tools/reference_overlays/check_task_stacks.py").read_bytes()


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
