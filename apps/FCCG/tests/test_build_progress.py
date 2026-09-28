from __future__ import annotations

import ast
import os
from pathlib import Path

from silverstar_fccg.build.runner import (
    BuildAction,
    BuildProgress,
    BuildRunner,
)
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.task import (
    TaskContext,
    TaskProgressEvent_Parse,
    TaskProgressState,
)
from silverstar_fccg.project.model import ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create


def _BuildRoot_Create(tmp_path: Path):
    root = tmp_path / "BuildProgress"
    root.mkdir()
    model = ReferenceProject_Create("BuildProgress")
    policy = WorkspacePolicy(root)
    ProjectModel_Save(model, root / "SilverStar.ssproject", policy)
    (root / "Makefile").write_text(
        "# SilverStar authoritative build entry\n.PHONY: all\nall:\n\t@echo ok\n",
        encoding="utf-8",
    )
    return root, model, BuildRunner(policy)


def test_validation_build_uses_release_without_project_state(
    tmp_path: Path,
) -> None:
    _root, model, runner = _BuildRoot_Create(tmp_path)

    command = runner.Command_Get(model, BuildAction.BUILD)

    assert "CONFIG=Release" in command
    assert command[-1] == "all"
    assert "configuration" not in model.Dictionary_Get()["build"]


def test_host_tests_override_inherited_compiler_and_windows_make_shell(
    tmp_path: Path, monkeypatch
) -> None:
    _root, model, runner = _BuildRoot_Create(tmp_path)
    host_compiler = tmp_path / "Native Host GCC" / "gcc.exe"
    host_compiler.parent.mkdir()
    host_compiler.write_bytes(b"")
    eide_directory = tmp_path / "EIDE" / "scripts"
    eide_directory.mkdir(parents=True)
    monkeypatch.setenv("HOST_CC", "unexpected-global-compiler")
    monkeypatch.setenv("SHELL", "powershell")
    monkeypatch.setenv("MAKESHELL", "sh.exe")
    monkeypatch.setenv("COMPILER_PATH", "unexpected-compiler-path")
    monkeypatch.setenv("LIBRARY_PATH", "unexpected-library-path")
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(eide_directory), os.environ.get("PATH", ""))),
    )
    monkeypatch.setattr(
        "silverstar_fccg.build.runner.shutil.which",
        lambda command: str(host_compiler) if command == "gcc" else None,
    )

    command = runner.Command_Get(model, BuildAction.HOST_TESTS)
    environment = runner._Environment_Get(model, BuildAction.HOST_TESTS)

    host_argument = next(value for value in command if value.startswith("HOST_CC="))
    assert host_argument == f"HOST_CC={host_compiler.resolve().as_posix()}"
    assert Path(environment["PATH"].split(os.pathsep)[0]) == host_compiler.parent
    assert "COMPILER_PATH" not in environment
    assert "LIBRARY_PATH" not in environment
    if os.name == "nt":
        assert "SHELL" not in environment
        assert "MAKESHELL" not in environment


def test_dry_run_plans_incremental_steps_and_streams_live_progress(
    tmp_path: Path, monkeypatch
) -> None:
    root, model, runner = _BuildRoot_Create(tmp_path)
    calls: list[tuple[str, ...]] = []
    dry_lines = [
        f'echo "FCCG_PROGRESS|{stage}_{state}|{subject}"\n'
        for stage, subject in (
            ("COMPILE", "APP/Src/one.c"),
            ("LINK", "build/app.elf"),
            ("SIZE", "build/app.elf"),
            ("HEX", "build/app.hex"),
            ("BIN", "build/app.bin"),
        )
        for state in ("BEGIN", "DONE")
    ]
    actual_lines = [
        "FCCG_PROGRESS|COMPILE_BEGIN|APP/Src/one.c\n",
        "compiler output\n",
        "FCCG_PROGRESS|COMPILE_DONE|APP/Src/one.c\n",
        "FCCG_PROGRESS|LINK_BEGIN|build/app.elf\n",
        "FCCG_PROGRESS|LINK_DONE|build/app.elf\n",
        "FCCG_PROGRESS|SIZE_BEGIN|build/app.elf\n",
        "FCCG_PROGRESS|SIZE_DONE|build/app.elf\n",
        "FCCG_PROGRESS|HEX_BEGIN|build/app.hex\n",
        "FCCG_PROGRESS|HEX_DONE|build/app.hex\n",
        "FCCG_PROGRESS|BIN_BEGIN|build/app.bin\n",
        "FCCG_PROGRESS|BIN_DONE|build/app.bin\n",
    ]

    def process_run(command, _root, _environment, _token, line_callback=None):
        calls.append(tuple(command))
        lines = dry_lines if "-n" in command else actual_lines
        if line_callback is not None:
            for line in lines:
                line_callback(line)
        return 0, list(lines)

    monkeypatch.setattr(BuildRunner, "_Process_Run", staticmethod(process_run))
    live_lines: list[str] = []
    progress: list[BuildProgress] = []

    result = runner.Run(
        model,
        root,
        BuildAction.BUILD,
        line_callback=live_lines.append,
        progress_callback=progress.append,
    )

    assert result.succeeded
    assert result.plan.total_steps == 5
    assert result.plan.compile_steps == 1
    assert result.completed_steps == 5
    assert calls[0][1] == "-n"
    assert live_lines == ["compiler output"]
    assert progress[0].stage == "PLAN"
    assert [item.stage for item in progress[1:-1]] == [
        stage
        for stage in ("COMPILE", "LINK", "SIZE", "HEX", "BIN")
        for _state in ("BEGIN", "DONE")
    ]
    assert progress[1].completed_steps == 0
    assert progress[2].completed_steps == 1
    assert progress[-1].stage == "COMPLETE"
    assert progress[-1].completed_steps == progress[-1].total_steps == 5


def test_generic_progress_advances_only_on_done_and_failure_stays_partial(
    tmp_path: Path, monkeypatch
) -> None:
    root, model, runner = _BuildRoot_Create(tmp_path)
    actual_lines = [
        "FCCG_PROGRESS|HOST_TEST|PLAN|2\n",
        "FCCG_PROGRESS|HOST_TEST|BEGIN|1|2|interfaces\n",
        "FCCG_PROGRESS|HOST_TEST|DONE|1|2|interfaces\n",
        "FCCG_PROGRESS|HOST_TEST|BEGIN|2|2|sensor_status\n",
        "FCCG_DETAIL|compiler diagnostic\n",
    ]

    def process_run(command, _root, _environment, _token, line_callback=None):
        lines = [] if "-n" in command else actual_lines
        if line_callback is not None:
            for line in lines:
                line_callback(line)
        return (0 if "-n" in command else 1), list(lines)

    monkeypatch.setattr(BuildRunner, "_Process_Run", staticmethod(process_run))
    progress: list[BuildProgress] = []
    live_lines: list[str] = []

    result = runner.Run(
        model,
        root,
        BuildAction.BUILD,
        line_callback=live_lines.append,
        progress_callback=progress.append,
    )

    assert not result.succeeded
    assert result.plan.total_steps == 2
    assert result.completed_steps == 1
    assert progress[-1].stage == "HOST_TEST"
    assert progress[-1].completed_steps == 1
    assert progress[-1].total_steps == 2
    assert all(item.stage != "COMPLETE" for item in progress)
    assert live_lines == ["FCCG_DETAIL|compiler diagnostic"]


def test_clean_all_make_progress_is_determinate_and_failure_stays_partial(
    tmp_path: Path, monkeypatch
) -> None:
    root, model, runner = _BuildRoot_Create(tmp_path)
    (root / "Makefile").write_text(
        "# SilverStar authoritative build entry\n"
        ".PHONY: clean-all\n"
        "clean-all:\n"
        "\t@echo ok\n",
        encoding="utf-8",
    )
    actual_lines = [
        '"FCCG_PROGRESS|CLEAN_ALL|PLAN|3"\n',
        '"FCCG_PROGRESS|CLEAN_ALL|BEGIN|1|3|build/FCCG"\n',
        '"FCCG_PROGRESS|CLEAN_ALL|DONE|1|3|build/FCCG"\n',
        '"FCCG_PROGRESS|CLEAN_ALL|BEGIN|2|3|.eide/build"\n',
    ]

    def process_run(command, _root, _environment, _token, line_callback=None):
        if line_callback is not None:
            for line in actual_lines:
                line_callback(line)
        return 1, list(actual_lines)

    monkeypatch.setattr(BuildRunner, "_Process_Run", staticmethod(process_run))
    progress: list[BuildProgress] = []
    live_lines: list[str] = []

    result = runner.Run(
        model,
        root,
        BuildAction.CLEAN_ALL,
        line_callback=live_lines.append,
        progress_callback=progress.append,
    )

    assert not result.succeeded
    assert result.plan.total_steps == 3
    assert result.completed_steps == 1
    assert progress[-1].stage == "CLEAN_ALL"
    assert progress[-1].completed_steps == 1
    assert progress[-1].total_steps == 3
    assert all(item.stage != "COMPLETE" for item in progress)
    assert live_lines == []
    assert TaskProgressEvent_Parse(actual_lines[0]).total == 3


def test_task_context_has_one_line_surface_and_structured_progress(
    workspace_root: Path,
) -> None:
    task_source = (
        workspace_root / "src" / "silverstar_fccg" / "core" / "task.py"
    ).read_text(encoding="utf-8")
    module = ast.parse(task_source)
    task_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "TaskContext"
    )
    field_names = [
        node.target.id
        for node in task_class.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    ]
    method_names = [
        node.name for node in task_class.body if isinstance(node, ast.FunctionDef)
    ]
    assert field_names.count("line_callback") == 1
    assert method_names.count("Line_Report") == 1

    progress_values: list[tuple[float, str]] = []
    lines: list[str] = []
    context = TaskContext(
        progress_callback=lambda value, code: progress_values.append((value, code)),
        line_callback=lines.append,
    )
    context.ProgressEvent_Report("SAVE", TaskProgressState.PLAN, total=2)
    context.ProgressEvent_Report(
        "SAVE", TaskProgressState.BEGIN, current=1, total=2, subject="validate"
    )
    context.ProgressEvent_Report(
        "SAVE", TaskProgressState.DONE, current=1, total=2, subject="validate"
    )

    assert [value for value, _code in progress_values] == [0.0, 0.0, 0.5]
    assert TaskProgressEvent_Parse(lines[0]).state == TaskProgressState.PLAN
    assert TaskProgressEvent_Parse(lines[1]).state == TaskProgressState.BEGIN
    assert TaskProgressEvent_Parse(lines[2]).state == TaskProgressState.DONE
    assert TaskProgressEvent_Parse("FCCG_PROGRESS|SAVE|PLAN|0") is None


def test_generated_quality_scripts_declare_real_progress_and_neutral_rejections(
    workspace_root: Path,
) -> None:
    payload = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
    )
    host = (payload / "Tests" / "Host" / "run_tests.ps1").read_text(
        encoding="utf-8"
    )
    assert "FCCG_PROGRESS|$taskKind|PLAN|$total" in host
    assert "FCCG_PROGRESS|$Task|BEGIN|$current|$total|$Subject" in host
    assert "FCCG_PROGRESS|$Task|DONE|$current|$total|$Subject" in host
    assert "FCCG_EXPECTED_REJECTION|$Name" in host
    assert "FCCG_DETAIL|$Text" in host
    assert "host-tests-detail.log" in host
    assert "Host compiler runtime directory:" in host
    assert "$hostCompilerDirectory + [System.IO.Path]::PathSeparator" in host
    assert "'COMPILER_PATH'" in host
    assert "'LIBRARY_PATH'" in host
    assert 'Write-Output "Expected host compile failure passed:' not in host

    architecture = (
        payload / "Tools" / "check_architecture.ps1"
    ).read_text(encoding="utf-8")
    power10 = (payload / "Tools" / "check_power_of_ten.ps1").read_text(
        encoding="utf-8"
    )
    artifact = (
        payload / "Tools" / "check_firmware_artifact.ps1"
    ).read_text(encoding="utf-8")
    assert "FCCG_PROGRESS|ARCHITECTURE|PLAN|6" in architecture
    for subject in (
        "source_graph",
        "eide_consistency",
        "protocol",
        "freertos",
        "directory_boundaries",
        "summary",
    ):
        assert subject in architecture
    assert "FCCG_PROGRESS|POWER10|PLAN|$progressTotal" in power10
    assert "FCCG_PROGRESS|ARTIFACT|PLAN|8" in artifact
    for subject in ("ELF", "MAP", "FLASH", "MAIN_SRAM", "CCMRAM", "heap"):
        assert subject in artifact
