from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Protocol

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.task import (
    TaskProgressEvent_Parse,
    TaskProgressState,
)
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.lifecycle import MakefileTarget_Has
from silverstar_fccg.project.model import ProjectModel


class CancellationToken(Protocol):
    @property
    def cancelled(self) -> bool: ...


class BuildAction(StrEnum):
    CLEAN = "clean"
    CLEAN_ALL = "clean_all"
    BUILD = "build"
    HOST_TESTS = "host_tests"
    ARCHITECTURE_CHECK = "architecture_check"
    POWER10_CHECK = "power10_check"
    STATIC_ANALYSIS = "static_analysis"
    ARTIFACT_CHECK = "artifact_check"

    def MakeTarget_Get(self) -> str:
        return {
            BuildAction.CLEAN: "clean",
            BuildAction.CLEAN_ALL: "clean-all",
            BuildAction.BUILD: "all",
            BuildAction.HOST_TESTS: "host-tests",
            BuildAction.ARCHITECTURE_CHECK: "architecture-check",
            BuildAction.POWER10_CHECK: "power10-check",
            BuildAction.STATIC_ANALYSIS: "static-analysis",
            BuildAction.ARTIFACT_CHECK: "artifact-check",
        }[self]

    def Configuration_Get(self) -> str:
        return "Release"


@dataclass(frozen=True, slots=True)
class BuildPlan:
    total_steps: int
    compile_steps: int
    stage_steps: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class BuildProgress:
    stage: str
    completed_steps: int
    total_steps: int
    subject: str = ""
    stage_completed: int = 0
    stage_total: int = 0


@dataclass(frozen=True, slots=True)
class BuildResult:
    action: BuildAction
    command: tuple[str, ...]
    return_code: int
    output: str
    plan: BuildPlan = BuildPlan(0, 0)
    completed_steps: int = 0
    live_streamed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


LineCallback = Callable[[str], None]
ProgressCallback = Callable[[BuildProgress], None]


class BuildRunner:
    _PROGRESS_PATTERN = re.compile(
        r"FCCG_PROGRESS\|(COMPILE|LINK|HEX|BIN|SIZE)_(BEGIN|DONE)\|"
        r"([^\r\n\"]+)"
    )

    @staticmethod
    def _Stage_Normalize(
        action: BuildAction, stage: str, subject: str
    ) -> str:
        if action != BuildAction.STATIC_ANALYSIS or stage != "COMPILE":
            return stage
        normalized = subject.replace("\\", "/")
        first_party_roots = (
            "APP/",
            "Algorithm/",
            "Board/",
            "Common/",
            "Devices/",
            "FlightLogic/",
            "Generated/",
            "Interfaces/",
            "Modules/",
            "OS/FreeRTOS/",
            "Platform/",
            "Protocol/",
            "System/",
            "Targets/",
        )
        return (
            "ANALYZE"
            if normalized.startswith(first_party_roots)
            else "DEPENDENCY_COMPILE"
        )

    def __init__(self, policy: WorkspacePolicy) -> None:
        self.policy = policy

    @staticmethod
    def _HostCompiler_Resolve(model: ProjectModel) -> Path | None:
        configured = model.build.tool_paths.get("host_gcc", "").strip()
        if configured:
            return Path(configured).resolve()
        discovered = shutil.which("gcc")
        return Path(discovered).resolve() if discovered else None

    def Command_Get(self, model: ProjectModel, action: BuildAction) -> tuple[str, ...]:
        tool_paths = model.build.tool_paths
        base = (
            tool_paths.get("make", model.build.make_command),
            f"TARGET_PROFILE={model.build.target_profile}",
            f"CONFIG={action.Configuration_Get()}",
        )
        overrides: list[str] = []
        memory_layout = getattr(model.build, "memory_layout", "legacy")
        if memory_layout != "legacy":
            overrides.append(f"MEMORY_LAYOUT={memory_layout}")
        compiler_path = tool_paths.get("compiler", model.build.gcc_path)
        if compiler_path:
            overrides.append(
                f"GCC_PATH={Path(compiler_path).resolve().parent.as_posix()}"
            )
        if action == BuildAction.HOST_TESTS:
            host_compiler = self._HostCompiler_Resolve(model)
            overrides.append(
                f"HOST_CC={host_compiler.as_posix()}"
                if host_compiler
                else "HOST_CC=gcc"
            )
        return (*base, *overrides, action.MakeTarget_Get())

    def Plan_Get(
        self,
        model: ProjectModel,
        project_root: Path,
        action: BuildAction,
        token: CancellationToken | None = None,
    ) -> BuildPlan:
        if action not in {
            BuildAction.BUILD,
            BuildAction.STATIC_ANALYSIS,
        }:
            return BuildPlan(1, 0, (("TASK", 1),))
        root = self.policy.Path_Resolve(project_root, allow_root=True)
        command = self.Command_Get(model, action)
        dry_run_command = (command[0], "-n", *command[1:])
        _return_code, lines = self._Process_Run(
            dry_run_command,
            root,
            self._Environment_Get(model, action),
            token,
        )
        markers = [
            match
            for line in lines
            for match in self._PROGRESS_PATTERN.finditer(line)
        ]
        completed_markers = [
            match for match in markers if match.group(2) == "DONE"
        ]
        if not completed_markers:
            return BuildPlan(1, 0, (("TASK", 1),))
        stages = Counter(
            self._Stage_Normalize(action, match.group(1), match.group(3).strip())
            for match in completed_markers
        )
        return BuildPlan(
            total_steps=len(completed_markers),
            compile_steps=sum(
                stages.get(stage, 0)
                for stage in ("COMPILE", "ANALYZE", "DEPENDENCY_COMPILE")
            ),
            stage_steps=tuple(
                (stage, stages.get(stage, 0))
                for stage in (
                    "COMPILE",
                    "ANALYZE",
                    "DEPENDENCY_COMPILE",
                    "LINK",
                    "SIZE",
                    "HEX",
                    "BIN",
                )
                if stages.get(stage, 0)
            ),
        )

    def Run(
        self,
        model: ProjectModel,
        project_root: Path,
        action: BuildAction,
        token: CancellationToken | None = None,
        *,
        line_callback: LineCallback | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> BuildResult:
        root = self._Project_Validate(project_root, action)
        command = self.Command_Get(model, action)
        environment = self._Environment_Get(model, action)
        plan = self.Plan_Get(model, root, action, token)
        if progress_callback is not None:
            progress_callback(
                BuildProgress(
                    "PLAN",
                    0,
                    plan.total_steps,
                    stage_total=plan.compile_steps,
                )
            )
        stage_totals = dict(plan.stage_steps)
        stage_completed: Counter[str] = Counter()
        completed = 0
        placeholder_plan = plan.stage_steps == (("TASK", 1),)
        generic_plan_seen = False

        def plan_refresh() -> None:
            nonlocal plan, completed
            completed = sum(stage_completed.values())
            total = sum(stage_totals.values())
            compile_steps = sum(
                stage_totals.get(stage, 0)
                for stage in ("COMPILE", "ANALYZE", "DEPENDENCY_COMPILE")
            )
            plan = BuildPlan(
                max(total, 1),
                compile_steps,
                tuple(stage_totals.items()),
            )

        def output_line(line: str) -> None:
            nonlocal completed, generic_plan_seen
            generic = TaskProgressEvent_Parse(line)
            if generic is not None:
                stage = generic.task
                if generic.state == TaskProgressState.PLAN:
                    if placeholder_plan and not generic_plan_seen:
                        stage_totals.clear()
                        stage_completed.clear()
                    generic_plan_seen = True
                    stage_totals[stage] = generic.total
                    plan_refresh()
                    if progress_callback is not None:
                        progress_callback(
                            BuildProgress(
                                "PLAN",
                                completed,
                                plan.total_steps,
                                subject=stage,
                                stage_completed=stage_completed[stage],
                                stage_total=generic.total,
                            )
                        )
                    return
                stage_totals[stage] = max(
                    stage_totals.get(stage, 0), generic.total
                )
                if generic.state == TaskProgressState.BEGIN:
                    stage_completed[stage] = max(
                        stage_completed[stage], generic.current - 1
                    )
                    displayed_stage_current = generic.current
                else:
                    stage_completed[stage] = max(
                        stage_completed[stage], generic.current
                    )
                    displayed_stage_current = stage_completed[stage]
                plan_refresh()
                if progress_callback is not None:
                    progress_callback(
                        BuildProgress(
                            stage=stage,
                            completed_steps=completed,
                            total_steps=plan.total_steps,
                            subject=generic.subject,
                            stage_completed=displayed_stage_current,
                            stage_total=stage_totals[stage],
                        )
                    )
                return
            match = self._PROGRESS_PATTERN.search(line)
            if match is None:
                if line_callback is not None:
                    line_callback(line.rstrip("\r\n"))
                return
            stage, marker_state, subject = match.groups()
            stage = self._Stage_Normalize(action, stage, subject.strip())
            if marker_state == "BEGIN":
                if progress_callback is not None:
                    progress_callback(
                        BuildProgress(
                            stage=stage,
                            completed_steps=completed,
                            total_steps=max(plan.total_steps, 1),
                            subject=subject.strip(),
                            stage_completed=stage_completed[stage],
                            stage_total=max(stage_totals.get(stage, 0), 1),
                        )
                    )
                return
            stage_completed[stage] += 1
            completed = sum(stage_completed.values())
            if progress_callback is not None:
                progress_callback(
                    BuildProgress(
                        stage=stage,
                        completed_steps=completed,
                        total_steps=max(plan.total_steps, completed),
                        subject=subject.strip(),
                        stage_completed=stage_completed[stage],
                        stage_total=max(
                            stage_totals.get(stage, 0), stage_completed[stage]
                        ),
                    )
                )

        return_code, lines = self._Process_Run(
            command,
            root,
            environment,
            token,
            output_line,
        )
        if return_code == 0 and completed < plan.total_steps:
            completed = plan.total_steps
        if progress_callback is not None and return_code == 0:
            progress_callback(
                BuildProgress(
                    "COMPLETE",
                    max(completed, plan.total_steps),
                    max(plan.total_steps, completed),
                    stage_completed=completed,
                    stage_total=max(plan.total_steps, completed),
                )
            )
        return BuildResult(
            action,
            command,
            return_code,
            "".join(lines),
            plan,
            completed,
            line_callback is not None,
        )

    def _Project_Validate(
        self, project_root: Path, action: BuildAction
    ) -> Path:
        root = self.policy.Path_Resolve(project_root, allow_root=True)
        if not (root / "SilverStar.ssproject").is_file():
            raise FccgError(
                "error.project_descriptor_missing",
                {"path": str(root)},
                f"Not an FCCG project: {root}",
            )
        makefile = root / "Makefile"
        if not makefile.is_file():
            raise FccgError(
                "error.makefile_missing",
                {"path": str(root)},
                f"Generated Makefile is missing: {makefile}",
            )
        try:
            makefile_text = makefile.read_text(encoding="utf-8")
        except OSError as error:
            raise FccgError(
                "error.makefile_unreadable",
                {"path": str(makefile)},
                str(error),
            ) from error
        target = action.MakeTarget_Get()
        if (
            "SilverStar authoritative build entry" not in makefile_text
            or not MakefileTarget_Has(makefile_text, target)
        ):
            raise FccgError(
                "error.make_target_missing",
                {"target": target},
                f"Generated Makefile does not provide target {target!r}",
            )
        return root

    @staticmethod
    def _Environment_Get(
        model: ProjectModel,
        action: BuildAction | None = None,
    ) -> dict[str, str]:
        environment = os.environ.copy()
        if os.name == "nt":
            # A SHELL inherited from MSYS, Git Bash, or PowerShell changes how
            # mingw32-make expands recipes.  Generated projects use the native
            # Windows command processor and invoke PowerShell explicitly.
            environment.pop("SHELL", None)
            environment.pop("MAKESHELL", None)

        preferred_directories: list[str] = []
        if action == BuildAction.HOST_TESTS:
            host_compiler = BuildRunner._HostCompiler_Resolve(model)
            if host_compiler is not None:
                # cc1.exe and the MinGW binutils load runtime DLLs through PATH.
                # EIDE and Arm toolchain launchers commonly prepend incompatible
                # libwinpthread/libstdc++ copies, which can make GCC exit 1 with
                # no diagnostic.  Keep the selected native GCC runtime first.
                preferred_directories.append(str(host_compiler.parent))
            for variable in (
                "GCC_EXEC_PREFIX",
                "COMPILER_PATH",
                "CPATH",
                "C_INCLUDE_PATH",
                "CPLUS_INCLUDE_PATH",
                "OBJC_INCLUDE_PATH",
                "LIBRARY_PATH",
                "DEPENDENCIES_OUTPUT",
                "SUNPRO_DEPENDENCIES",
            ):
                environment.pop(variable, None)

        override_directories = sorted(
            {
                str(Path(path).resolve().parent)
                for path in model.build.tool_paths.values()
                if path
            }
        )
        path_prefix = tuple(
            dict.fromkeys((*preferred_directories, *override_directories))
        )
        if path_prefix:
            environment["PATH"] = os.pathsep.join(
                (*path_prefix, environment.get("PATH", ""))
            )
        return environment

    @staticmethod
    def _Process_Run(
        command: tuple[str, ...],
        root: Path,
        environment: dict[str, str],
        token: CancellationToken | None,
        line_callback: LineCallback | None = None,
    ) -> tuple[int, list[str]]:
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=environment,
                bufsize=1,
            )
        except OSError as error:
            raise FccgError(
                "error.build_tool_start",
                {"tool": command[0]},
                str(error),
            ) from error

        queue: Queue[str | Exception | None] = Queue()

        def output_read() -> None:
            try:
                assert process.stdout is not None
                while True:
                    line = process.stdout.readline()
                    if line == "":
                        break
                    queue.put(line)
            except Exception as error:  # noqa: BLE001 - forward reader failures to caller
                queue.put(error)
            finally:
                queue.put(None)

        reader = Thread(target=output_read, daemon=True)
        reader.start()
        lines: list[str] = []
        stream_finished = False
        while not stream_finished or process.poll() is None:
            if token is not None and token.cancelled and process.poll() is None:
                process.terminate()
            try:
                line = queue.get(timeout=0.1)
            except Empty:
                continue
            if line is None:
                stream_finished = True
                continue
            if isinstance(line, Exception):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise FccgError(
                    "error.build_output_read",
                    {},
                    str(line),
                ) from line
            lines.append(line)
            if line_callback is not None:
                try:
                    line_callback(line)
                except Exception:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    raise
        return process.wait(), lines
