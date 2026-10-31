"""Read bounded task budgets tied to the exact linked ELF and checker.

This report does not prove main/MSP/ISR nesting or hardware high-water marks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError


_PREFIX = "artifact_stack_v1="


def ArtifactStackReportSummary_Encode(output: str, expected_root: Path) -> str:
    paths = re.findall(r"^FIRMWARE_STACK_REPORT\|(.+)$", output, re.MULTILINE)
    if len(paths) != 1:
        return ""
    try:
        path = Path(paths[0].strip())
        if not path.is_absolute() or path.stat().st_size > 4 * 1024 * 1024:
            return ""
        raw = path.read_bytes()
        report = json.loads(raw)
        if report["schema"] != "silverstar.stack-budget/1":
            return ""
        relative = PurePosixPath(report["elf"].replace("\\", "/"))
        if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2 or
                relative.suffix != '.elf' or report['configuration'] not in {'Release', 'Debug'} or
                relative.parent.name != report['configuration']):
            return ""
        root = path.parents[len(relative.parts) - 1]
        if root.absolute() != Path(expected_root).absolute():
            return ""
        policy = WorkspacePolicy(root)
        if policy.Path_Resolve(relative.parent / "stack-budget.json", allow_root=False) != path.absolute():
            return ""
        artifacts = {}
        for name, relative_path in (("elf", relative), ("checker", "Tools/check_task_stacks.py")):
            artifact_path = policy.Path_Resolve(relative_path, allow_root=False)
            with artifact_path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != report[name + "_sha256"]:
                return ""
            artifacts[name] = {"path": str(artifact_path), "sha256": digest}
        value = {key: report[key] for key in ("configuration", "compiler", "minimum_margin_bytes",
                 "tasks", "checks", "passes", "whole_program_stack_acceptance")}
        value.update(target="flight", report_path=str(path),
                     report_sha256=hashlib.sha256(raw).hexdigest(), artifacts=artifacts)
        summary = _PREFIX + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return summary if ArtifactStackReportSummary_Decode(summary) else ""
    except (OSError, ValueError, KeyError, TypeError, IndexError, WorkspacePolicyError):
        return ""


def ArtifactStackReportSummary_Decode(summary: str) -> dict | None:
    if not summary.startswith(_PREFIX) or len(summary) > 131072:
        return None
    try:
        value = json.loads(summary[len(_PREFIX):])
        if value["target"] != "flight" or type(value["passes"]) is not bool:
            return None
        if not str(value["whole_program_stack_acceptance"]).startswith("NOT PROVEN:"):
            return None
        minimum = value["minimum_margin_bytes"]
        if type(minimum) is not int or minimum < 0:
            return None
        if type(value["checks"]) is not dict or not value["checks"] or not all(
                type(item) is bool for item in value["checks"].values()):
            return None
        if type(value["tasks"]) is not list or not 1 <= len(value["tasks"]) <= 32:
            return None
        names = set()
        for task in value["tasks"]:
            name = task["task"]
            if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name) or name in names:
                return None
            names.add(name)
            for key in ("configured_bytes", "call_chain_bytes", "context_bytes", "worst_known_bytes"):
                if type(task[key]) is not int or task[key] < 0:
                    return None
            if (task["configured_bytes"] <= 0 or type(task["margin_bytes"]) is not int or
                    task["worst_known_bytes"] != task["call_chain_bytes"] + task["context_bytes"] or
                    task["margin_bytes"] != task["configured_bytes"] - task["worst_known_bytes"] or
                    type(task["passes"]) is not bool or task["passes"] != (task["margin_bytes"] >= minimum)):
                return None
            chain = task["chain"]
            if type(chain) is not list or not 1 <= len(chain) <= 128 or any(
                    type(frame["function"]) is not str or len(frame["function"]) > 256 or
                    type(frame["frame_bytes"]) is not int or frame["frame_bytes"] < 0 for frame in chain):
                return None
            if sum(frame['frame_bytes'] for frame in chain) != task['call_chain_bytes']:
                return None
        expected = all(value["checks"].values()) and all(task["passes"] for task in value["tasks"])
        if value["passes"] != expected:
            return None
        if (type(value['artifacts']) is not dict or set(value['artifacts']) != {'elf', 'checker'} or
                type(value['report_path']) is not str):
            return None
        for digest in (value["report_sha256"], *(item["sha256"] for item in value["artifacts"].values())):
            if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                return None
        return value
    except (ValueError, KeyError, TypeError):
        return None
