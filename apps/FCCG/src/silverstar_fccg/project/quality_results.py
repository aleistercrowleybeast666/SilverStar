from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy


QUALITY_RESULTS_RELATIVE_PATH = ".fccg/quality-results.json"


@dataclass(frozen=True, slots=True)
class QualityResultRecord:
    task: str
    result: str
    timestamp: str
    duration: float
    summary: str


def QualityResults_Load(project_root: Path) -> tuple[QualityResultRecord, ...]:
    policy = WorkspacePolicy(project_root)
    path = policy.Path_Resolve(QUALITY_RESULTS_RELATIVE_PATH, allow_root=False)
    if not path.is_file():
        return ()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(document, dict) or document.get("format_version") != 1:
        return ()
    values = document.get("results")
    if not isinstance(values, dict):
        return ()
    records: list[QualityResultRecord] = []
    for task, value in sorted(values.items()):
        if (
            not isinstance(task, str)
            or not isinstance(value, dict)
            or value.get("task") != task
            or value.get("result") not in {"passed", "failed"}
            or not isinstance(value.get("timestamp"), str)
            or isinstance(value.get("duration"), bool)
            or not isinstance(value.get("duration"), (int, float))
            or float(value["duration"]) < 0.0
            or not isinstance(value.get("summary"), str)
        ):
            continue
        records.append(
            QualityResultRecord(
                task=task,
                result=value["result"],
                timestamp=value["timestamp"],
                duration=float(value["duration"]),
                summary=value["summary"],
            )
        )
    return tuple(records)


def QualityResult_Save(
    project_root: Path,
    *,
    task: str,
    succeeded: bool,
    duration: float,
    summary: str,
) -> QualityResultRecord:
    policy = WorkspacePolicy(project_root)
    records = {record.task: record for record in QualityResults_Load(project_root)}
    record = QualityResultRecord(
        task=task,
        result="passed" if succeeded else "failed",
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        duration=max(0.0, float(duration)),
        summary=summary.strip(),
    )
    records[task] = record
    document = {
        "format_version": 1,
        "results": {
            task_id: asdict(saved)
            for task_id, saved in sorted(records.items())
        },
    }
    policy.Text_AtomicWrite(
        QUALITY_RESULTS_RELATIVE_PATH,
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return record
