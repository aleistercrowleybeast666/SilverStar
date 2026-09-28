from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import silverstar_fccg.generator.assembler as assembler_module
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildAction, BuildResult, BuildRunner
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.lifecycle import ProjectLifecycleState
from silverstar_fccg.project.logging import (
    LogPolicyLevel,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import ProjectModel_Load


def test_first_save_materializes_a_ready_dry_runnable_project(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "LifecycleProject"
    model = service.ReferenceProject_Create("LifecycleProject")

    assert service.ProjectReadiness_Get(model, project_root).state == (
        ProjectLifecycleState.DRAFT
    )

    service.Project_Save(model, project_root)

    readiness = service.ProjectReadiness_Get(model, project_root)
    assert readiness.state == ProjectLifecycleState.READY
    assert not readiness.missing
    assert not readiness.stale
    for relative in (
        "SilverStar.ssproject",
        "Makefile",
        ".fccg/hardware-preparation.json",
        ".fccg/ownership.json",
        ".eide/eide.yml",
        ".vscode/tasks.json",
        "LifecycleProject.code-workspace",
        "Flight_Controller0.5.ioc",
        "startup_stm32f407xx.s",
        "STM32F407XX_FLASH.ld",
    ):
        assert (project_root / relative).is_file(), relative
    for relative in ("BuildSystem", "Generated", "Targets/SilverStar_F407"):
        assert (project_root / relative).is_dir(), relative
    for relative in ("Core", "Drivers", "FATFS"):
        assert (project_root / relative).is_dir(), relative
    assert not (project_root / "HardwareGenerated").exists()

    make = shutil.which(model.build.make_command)
    if make is None:
        pytest.skip(f"{model.build.make_command} is not available")
    dry_run = subprocess.run(
        (
            make,
            "-C",
            str(project_root),
            "-n",
            f"TARGET_PROFILE={model.build.target_profile}",
            "CONFIG=Debug",
            "all",
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    makefile_text = (project_root / "Makefile").read_text(encoding="utf-8")
    assert "CONFIG ?= Release" in makefile_text
    assert "DEBUG_FLAGS := -g" in makefile_text
    assert "FCCG_PROGRESS|COMPILE_BEGIN|$<" in makefile_text
    assert "FCCG_PROGRESS|COMPILE_DONE|$<" in makefile_text
    assert "FCCG_PROGRESS|LINK_BEGIN|$@" in makefile_text
    assert "FCCG_PROGRESS|LINK_DONE|$@" in makefile_text


def test_generation_fingerprint_ignores_local_tools_and_recovers_after_mode_change(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "GenerationFingerprint"
    model = service.ReferenceProject_Create("GenerationFingerprint")

    service.Project_Save(model, project_root)
    assert service.ProjectReadiness_Get(model, project_root).ready

    model.build = replace(
        model.build,
        tool_paths={
            "compiler": str(tmp_path / "arm" / "arm-none-eabi-gcc.exe"),
            "make": str(tmp_path / "make" / "mingw32-make.exe"),
            "host_gcc": str(tmp_path / "host" / "gcc.exe"),
        },
        gcc_path=str(tmp_path / "legacy" / "gcc.exe"),
    )
    assert service.ProjectReadiness_Get(model, project_root).ready

    settings = SettingsStore(tmp_path / "generation-fingerprint-ui.ini")
    settings.Value_Set("theme", "dark")
    settings.Value_Set("language", "en_US")
    assert service.ProjectReadiness_Get(model, project_root).ready

    model.modes["deployment"].append("Delay")
    dirty = service.ProjectReadiness_Get(model, project_root)
    assert dirty.state == ProjectLifecycleState.DIRTY
    assert "SilverStar.ssproject" in dirty.stale

    service.Project_Save(model, project_root)
    assert service.ProjectReadiness_Get(model, project_root).ready


def test_readiness_detects_and_save_restores_a_missing_managed_file(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "ManagedReadiness"
    model = service.ReferenceProject_Create("ManagedReadiness")
    service.Project_Save(model, project_root)

    managed_file = project_root / ".vscode" / "settings.json"
    managed_file.unlink()
    readiness = service.ProjectReadiness_Get(model, project_root)
    assert readiness.state == ProjectLifecycleState.DIRTY
    assert ".vscode/settings.json" in readiness.missing

    service.Project_Save(model, project_root)
    assert managed_file.is_file()
    assert service.ProjectReadiness_Get(model, project_root).ready


def test_save_refreshes_managed_output_after_renderer_change(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "RendererRefresh"
    model = service.ReferenceProject_Create("RendererRefresh")
    service.Project_Save(model, project_root)
    settings_path = project_root / ".vscode" / "settings.json"
    original_settings = settings_path.read_bytes()
    original_renderer = assembler_module.MetadataFiles_Render

    def MetadataFiles_RenderChanged(*args, **kwargs):
        rendered = original_renderer(*args, **kwargs)
        rendered[".vscode/settings.json"] += b"\n"
        return rendered

    monkeypatch.setattr(
        assembler_module,
        "MetadataFiles_Render",
        MetadataFiles_RenderChanged,
    )

    result = service.Project_Save(model, project_root)

    assert result.files_modified >= 2
    assert settings_path.read_bytes() == original_settings + b"\n"
    assert service.ProjectReadiness_Get(model, project_root).ready


def test_verified_board_preparation_is_idempotent(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "PreparedBoard"
    model = service.ReferenceProject_Create("PreparedBoard")
    monkeypatch.setattr(
        type(service.hardware_importer),
        "Project_Import",
        lambda *_args, **_kwargs: pytest.fail(
            "verified Board preparation must not invoke CubeMX import/generation"
        ),
    )

    first = service.Project_HardwarePrepare(model, project_root)
    marker = project_root / ".fccg" / "hardware-preparation.json"
    marker_content = marker.read_bytes()
    second = service.Project_HardwarePrepare(model, project_root)

    assert first.files_added > 0
    assert second.files_added == 0
    assert second.files_modified == 0
    assert marker.read_bytes() == marker_content
    assert service.Project_HardwarePrepared_Is(model, project_root)


def test_first_save_publishes_project_descriptor_last(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "DescriptorLast"
    model = service.ReferenceProject_Create("DescriptorLast")
    published: list[Path] = []
    original_replace = WorkspacePolicy.Path_Replace

    def path_replace(self, source, destination, *, attempts=5) -> Path:
        target = Path(destination)
        if target.parent == project_root:
            published.append(target)
        return original_replace(
            self,
            source,
            destination,
            attempts=attempts,
        )

    monkeypatch.setattr(WorkspacePolicy, "Path_Replace", path_replace)
    service.Project_Save(model, project_root)

    assert published
    assert published[-1] == project_root / "SilverStar.ssproject"
    assert service.ProjectReadiness_Get(model, project_root).ready


def test_build_auto_saves_dirty_mode_and_logging_configuration(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "BuildAutoSave"
    model = service.ReferenceProject_Create("BuildAutoSave")
    service.Project_Save(model, project_root)

    model.modes["deployment"] = ["ApogeeVerticalVelocity", "Tilt"]
    definitions = {
        definition.record: definition
        for definition in ProtocolLogDefinitions_Get(model, service.catalog)
    }
    optional = next(
        stream
        for stream in model.logging_streams
        if definitions[stream.record].level != LogPolicyLevel.REQUIRED
    )
    model.logging_streams = [
        replace(stream, enabled=False) if stream.record == optional.record else stream
        for stream in model.logging_streams
    ]

    def build_run(
        _runner: BuildRunner,
        current_model,
        current_root: Path,
        action: BuildAction,
        _token=None,
    ) -> BuildResult:
        saved = ProjectModel_Load(current_root / "SilverStar.ssproject")
        assert saved.modes["deployment"] == ["ApogeeVerticalVelocity", "Tilt"]
        assert not next(
            stream
            for stream in saved.logging_streams
            if stream.record == optional.record
        ).enabled
        assert service.ProjectReadiness_Get(current_model, current_root).ready
        return BuildResult(action, ("test-make", action.MakeTarget_Get()), 0, "ok\n")

    monkeypatch.setattr(BuildRunner, "Run", build_run)
    result = service.Build_Run(model, project_root, BuildAction.BUILD)
    assert result.succeeded


def test_all_advanced_actions_use_ensure_buildable_and_project_root(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "AdvancedActions"
    model = service.ReferenceProject_Create("AdvancedActions")
    service.Project_Save(model, project_root)
    actions = (
        BuildAction.HOST_TESTS,
        BuildAction.ARCHITECTURE_CHECK,
        BuildAction.POWER10_CHECK,
        BuildAction.STATIC_ANALYSIS,
        BuildAction.ARTIFACT_CHECK,
    )
    ensure_calls: list[Path] = []
    run_calls: list[tuple[Path, BuildAction]] = []
    original_ensure = service.Project_EnsureBuildable

    def ensure_buildable(current_model, current_root: Path, **kwargs):
        ensure_calls.append(current_root.resolve())
        return original_ensure(current_model, current_root, **kwargs)

    def build_run(
        _runner: BuildRunner,
        _model,
        current_root: Path,
        action: BuildAction,
        _token=None,
    ) -> BuildResult:
        run_calls.append((current_root.resolve(), action))
        return BuildResult(action, ("test-make", action.MakeTarget_Get()), 0, "ok\n")

    monkeypatch.setattr(service, "Project_EnsureBuildable", ensure_buildable)
    monkeypatch.setattr(BuildRunner, "Run", build_run)
    for action in actions:
        assert service.Build_Run(model, project_root, action).succeeded

    assert ensure_calls == [project_root.resolve()] * len(actions)
    assert run_calls == [(project_root.resolve(), action) for action in actions]
    makefile = (project_root / "Makefile").read_text(encoding="utf-8")
    assert "artifact-check: all" in makefile


def test_build_runner_starts_make_with_explicit_project_cwd(
    tmp_path: Path, workspace_root: Path, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "RunnerCwd"
    model = service.ReferenceProject_Create("RunnerCwd")
    service.Project_Save(model, project_root)
    calls: list[tuple[tuple[str, ...], Path]] = []

    class FakeStdout:
        def __init__(self) -> None:
            self._lines = iter(("checked\n", ""))

        def readline(self) -> str:
            return next(self._lines)

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()

        def poll(self) -> int:
            return 0

        def wait(self) -> int:
            return 0

        def terminate(self) -> None:
            raise AssertionError("completed fake process must not be terminated")

    def process_start(command, **kwargs):
        calls.append((tuple(command), Path(kwargs["cwd"])))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", process_start)
    runner = BuildRunner(WorkspacePolicy(project_root))
    for action in (
        BuildAction.HOST_TESTS,
        BuildAction.ARCHITECTURE_CHECK,
        BuildAction.POWER10_CHECK,
        BuildAction.STATIC_ANALYSIS,
        BuildAction.ARTIFACT_CHECK,
    ):
        assert runner.Run(model, project_root, action).succeeded

    assert [command[-1] for command, _root in calls] == [
        "host-tests",
        "architecture-check",
        "power10-check",
        "static-analysis",
        "static-analysis",
        "artifact-check",
    ]
    assert calls[3][0][1] == "-n"
    assert calls[4][0][1] != "-n"
    assert all(root == project_root.resolve() for _command, root in calls)


def test_advanced_build_defaults_release_and_generated_debug_remains_available(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "BuildConfigurations"
    model = service.ReferenceProject_Create("BuildConfigurations")
    service.Project_Save(model, project_root)
    runner = BuildRunner(WorkspacePolicy(project_root))

    validation_command = runner.Command_Get(model, BuildAction.BUILD)
    assert "CONFIG=Release" in validation_command

    makefile = (project_root / "Makefile").read_text(encoding="utf-8")
    tasks = (project_root / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    eide = (project_root / ".eide" / "eide.yml").read_text(encoding="utf-8")
    assert "CONFIG ?= Release" in makefile
    assert "OPT := -Og" in makefile
    assert "DEBUG_FLAGS := -g3 -gdwarf-2" in makefile
    assert "OPT := -O2" in makefile
    assert "CONFIG must be Debug or Release" in makefile
    assert "NDEBUG" not in makefile
    assert "BUILD_ROOT := build/FCCG/$(TARGET_PROFILE)/StaticAnalysis/$(CONFIG)" in makefile
    assert "FIRST_PARTY_WARNINGS += -fanalyzer" in makefile
    assert "powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1" in makefile
    assert "# FCCG cleanup contract: determinate-v1" in makefile
    assert "FCCG_PROGRESS|CLEAN|PLAN|1" in makefile
    assert "FCCG_PROGRESS|CLEAN_ALL|PLAN|3" in makefile
    assert "$$paths" not in makefile
    assert "foreach ($$path" not in makefile
    assert (
        "Remove-Item -LiteralPath 'build/FCCG' -Recurse -Force "
        "-ErrorAction Stop"
    ) in makefile
    assert tasks.index("SilverStar: Build Release") < tasks.index(
        "SilverStar: Build Debug"
    )
    assert "SilverStar: Clean FCCG Build Outputs" in tasks
    assert "SilverStar: Clean All Build Outputs" in tasks
    assert "SilverStar: Clean Release" not in tasks
    assert "SilverStar: Clean Debug" not in tasks
    assert '"isDefault": true' in tasks
    assert eide.index("  Release:") < eide.index("  Debug:")
    assert "deviceName: null" in eide
    assert "packDir: null" in eide
    assert re.search(r"(?m)^  uid: [0-9a-f]{32}$", eide)
    workspace = (
        project_root / "BuildConfigurations.code-workspace"
    ).read_text(encoding="utf-8")
    assert '"path": "."' in workspace
    configuration = (project_root / "SilverStar_Configuration.md").read_text(
        encoding="utf-8"
    )
    assert "- Board: `SS0.5`" in configuration
    assert "SilverStar 0.5" not in configuration

    power_service = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_device_sensor_input_voltage"
        / "payload"
        / "Devices"
        / "Power"
        / "InputVoltage"
        / "Src"
        / "power_service.c"
    ).read_text(encoding="utf-8")
    assert 'model_name = "SS0.5 Voltage Input"' in power_service
    assert "SilverStar 0.5 Voltage Input" not in power_service
    configuration = (project_root / "SilverStar_Configuration.md").read_text(
        encoding="utf-8"
    )
    assert "- Board: `SS0.5`" in configuration
    assert "SilverStar 0.5" not in configuration


def test_power_of_ten_violation_fixture_fails(
    tmp_path: Path, workspace_root: Path
) -> None:
    fixture_root = tmp_path / "power10-violation"
    tools_root = fixture_root / "Tools"
    app_root = fixture_root / "APP"
    tools_root.mkdir(parents=True)
    app_root.mkdir()
    script = tools_root / "check_power_of_ten.ps1"
    shutil.copy2(
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
        / "Tools"
        / "check_power_of_ten.ps1",
        script,
    )
    body = "\n".join(f"    value += {index};" for index in range(24))
    (app_root / "power10_violation.c").write_text(
        "static int PowerTenFixture_Run(void)\n"
        "{\n"
        "    int value = 0;\n"
        f"{body}\n"
        "    return value;\n"
        "}\n",
        encoding="utf-8",
    )
    (fixture_root / "Makefile").write_text(
        "FIRST_PARTY_C_SOURCES := APP/power10_violation.c\n"
        "FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror "
        "-Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 "
        "-Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes "
        "-Wmissing-prototypes -Wswitch-enum -Wvla\n"
        "power10-check:\n\t@echo check\n",
        encoding="utf-8",
    )
    (fixture_root / "STM32F407XX_FLASH.ld").write_text(
        "_Min_Heap_Size = 0x0;\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "runtime assertions" in output


def test_repeated_apply_preserves_managed_mtimes_and_build_dependencies(
    tmp_path: Path, workspace_root: Path
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "IncrementalApply"
    model = service.ReferenceProject_Create("IncrementalApply")
    service.Project_Save(model, project_root)
    tracked = (
        project_root / "Generated" / "Src" / "project_metadata.c",
        project_root / "Makefile",
        project_root / ".eide" / "eide.yml",
    )
    mtimes = {path: path.stat().st_mtime_ns for path in tracked}
    dependency = project_root / "build" / "SilverStar_F407" / "Release" / "keep.d"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("keep.o: keep.c\n", encoding="utf-8")

    result = service.Project_Save(model, project_root)

    assert result.files_added == 0
    assert result.files_modified == 0
    assert {path: path.stat().st_mtime_ns for path in tracked} == mtimes
    assert dependency.read_text(encoding="utf-8") == "keep.o: keep.c\n"


@pytest.mark.parametrize(
    ("relative", "condition", "allowed"),
    [
        ("APP/Src/estimator_task.c", "SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U", True),
        ("APP/Src/estimator_task.c", "SYSTEM_BUILD_ESTIMATOR_ENABLED == 0U", True),
        ("APP/Src/other.c", "SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U", False),
        ("APP/Src/estimator_task.c", "SYSTEM_BUILD_ESTIMATOR_ENABLED == 1U", False),
    ],
)
def test_power_of_ten_estimator_conditional_is_scoped(
    tmp_path: Path, workspace_root: Path, relative: str,
    condition: str, allowed: bool
) -> None:
    root = tmp_path / "estimator-conditional"
    script = root / "Tools/check_power_of_ten.ps1"
    script.parent.mkdir(parents=True)
    shutil.copy2(
        workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/Tools"
        / "check_power_of_ten.ps1", script
    )
    source = root / relative
    source.parent.mkdir(parents=True)
    source.write_text(
        f"#if ({condition})\n"
        "static int Fixture_Value(void) { return 1; }\n"
        "#else\n"
        "static int Fixture_Value(void) { return 0; }\n"
        "#endif\n",
        encoding="utf-8",
    )
    (root / "Makefile").write_text(
        f"FIRST_PARTY_C_SOURCES := {relative}\n"
        "FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror "
        "-Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 "
        "-Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes "
        "-Wmissing-prototypes -Wswitch-enum -Wvla\n"
        "power10-check:\n\t@echo check\n",
        encoding="utf-8",
    )
    (root / "STM32F407XX_FLASH.ld").write_text(
        "_Min_Heap_Size = 0x0;\n", encoding="utf-8"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(script)],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )
    output = completed.stdout + completed.stderr
    if allowed:
        assert completed.returncode == 0, output
        assert "Power of Ten check passed:" in output
    else:
        assert completed.returncode != 0
        assert "conditional compilation violation" in output
