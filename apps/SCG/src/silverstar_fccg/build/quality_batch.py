"""Run explicitly selected generated targets independently, with real events."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from silverstar_fccg.build.runner import BuildAction, BuildResult, BuildRunner
from silverstar_fccg.core.task import TaskCancelledError
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.project.power10_report import Power10TextPassed_Is
from silverstar_fccg.project.quality_inputs import QualityInputHash_Get


@dataclass(frozen=True)
class TargetQualityResult:
    target: str
    root: Path
    model: ProjectModel
    result: BuildResult | None
    input_sha256: str
    duration: float
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return bool(not self.error and self.result and self.result.succeeded and
                    (self.result.action != BuildAction.POWER10_CHECK or
                     Power10TextPassed_Is(self.result.output, self.result.return_code)))


@dataclass
class QualityBatchResult:
    targets: tuple[TargetQualityResult, ...]
    evidence_saved: bool = True

    @property
    def succeeded(self) -> bool:
        return bool(self.targets) and self.evidence_saved and all(target.succeeded for target in self.targets)


def QualityBatch_Run(inputs: tuple[tuple[str, Path, ProjectModel], ...], action: BuildAction,
                     context) -> QualityBatchResult:
    outcomes = []

    def emit(target: str, kind: str, **values) -> None:
        context.Line_Report("FCCG_QUALITY|" + json.dumps(dict(target=target, kind=kind, **values)))

    for index, (target, root, model) in enumerate(inputs):
        context.Cancel_RaiseIfRequested()
        start = time.perf_counter()
        runner = BuildRunner(WorkspacePolicy(root))
        command = runner.Command_Get(model, action)
        result = None
        digest = ""
        error = ""
        emit(target, "begin", action=action.value)
        try:
            before = QualityInputHash_Get(root, target, action.value, command, include_artifacts=False)

            def progress(value) -> None:
                # PLAN / unknown phases stay indeterminate, not a timed percentage.
                known = value.stage not in {"PLAN", "TASK", "UNMEASURED", "NO_WORK"}
                fraction = (value.completed_steps / value.total_steps
                            if known and value.total_steps else None)
                emit(target, "progress", fraction=fraction, stage=value.stage,
                     current=value.stage_completed, total=value.stage_total, subject=value.subject)
                if fraction is not None:
                    context.Progress_Report(min(0.99, (index + fraction) / len(inputs)), "status.build_running")

            result = runner.Run(model, root, action, context,
                line_callback=lambda line: emit(target, "line", line=line),
                progress_callback=progress, target_kind=target)
            context.Cancel_RaiseIfRequested()
            after = QualityInputHash_Get(root, target, action.value, command, include_artifacts=False)
            if before != after:
                error = "Generated inputs changed during this check; result is NOT PROVEN"
            else:
                digest = QualityInputHash_Get(root, target, action.value, command)
        except TaskCancelledError:
            raise
        except Exception as exception:
            error = str(exception)
        outcome = TargetQualityResult(target, root, model, result, digest,
                                      time.perf_counter() - start, error)
        outcomes.append(outcome)
        emit(target, "done", succeeded=outcome.succeeded, error=error)
        context.Progress_Report(min(0.99, (index + 1) / len(inputs)), "status.build_running")
    return QualityBatchResult(tuple(outcomes))
