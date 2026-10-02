"""Auditable text-check report, explicitly separate from manual acceptance."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel

REPORT_PATH = ".fccg/power10-report.json"


def Power10ConfigurationHash_Get(model: ProjectModel) -> str:
    return hashlib.sha256(json.dumps(model.Dictionary_Get(), sort_keys=True,
                                    ensure_ascii=True).encode()).hexdigest()


def Power10TextPassed_Is(output: str, return_code: int) -> bool:
    totals = re.findall(r"^POWER10_RULE5\|[^\r\n]*\|eligible_assertions=(\d+)\|", output, re.M)
    return (return_code == 0 and len(totals) == 1 and int(totals[0]) > 0
            and "POWER10_CONTRACT_REVIEW|FAIL|" not in output
            and "Power of Ten check FAILED" not in output)


def Power10Report_Create(root: Path, model: ProjectModel, output: str, return_code: int) -> dict:
    policy = WorkspacePolicy(root)
    functions = []
    for line in output.splitlines():
        if line.startswith("POWER10_RULE5_FUNCTION|"):
            fields = line.split("|")
            if len(fields) != 7:
                raise ValueError("Malformed Power10 function report")
            _, target, file, actual_line, name, loc, candidates = fields
            path = policy.Path_Resolve(file, allow_root=False)
            functions.append(dict(target=target, file=file, full_path=str(path),
                                  line=int(actual_line), function=name, code_lines=int(loc),
                                  runtime_candidates=int(candidates)))
    names = {item["file"] for item in functions}
    names.update(line.split("|")[1] for line in output.splitlines() if line.startswith("POWER10_SOURCE|") and len(line.split("|")) == 3)
    names.update(("Tools/check_power_of_ten.ps1", "Makefile", "SilverStar.ssproject"))
    hashes = {name: hashlib.sha256(policy.Path_Resolve(name, allow_root=False).read_bytes()).hexdigest()
              for name in sorted(names)}
    for line in output.splitlines():
        if line.startswith("POWER10_SOURCE|"):
            fields = line.split("|")
            if len(fields) != 3 or hashes.get(fields[1]) != fields[2]:
                raise ValueError("Source changed since Power10 scanning")
    findings = [dict(item, reason="zero_runtime_candidates; nonblocking; manual_review_required")
                for item in functions if item["code_lines"] > 10 and item["runtime_candidates"] == 0]
    hard_failures = [line[2:] if line.startswith("- ") else line
                     for line in output.splitlines() if line.startswith("- ") or "POWER10_CONTRACT_REVIEW|FAIL|" in line]
    scopes = []
    for line in output.splitlines():
        if line.startswith("POWER10_FUNCTION_SCOPE|"):
            fields = line.split("|")
            if len(fields) != 6:
                raise ValueError("Malformed Power10 scope report")
            _, target, file, start, end, name = fields
            scopes.append((target, file, int(start), int(end), name))
    hard_findings = []
    failure_section = False
    current_reason = ""
    for line in output.splitlines():
        if "Power of Ten check FAILED" in line:
            failure_section = True
        if not failure_section:
            continue
        if line.startswith("- "):
            current_reason = line[2:]
        match = re.match(r"^\s*(?:- )?(.+?):(\d+):\s*(.*)$", line)
        if match:
            file, actual_line, detail = match.groups()
            path = policy.Path_Resolve(file, allow_root=False)
            actual = int(actual_line)
            scope = next((item for item in scopes if item[1] == file and item[2] <= actual <= item[3]), None)
            hard_findings.append(dict(file=file, full_path=str(path), line=actual,
                target=scope[0] if scope else "", function=scope[4] if scope else "file scope / NOT_PROVEN",
                reason="hard_failure; " + current_reason + "; " + detail))
    return dict(format_version=1, timestamp=datetime.now(timezone.utc).isoformat(),
                target_root=str(policy.root), configuration_sha256=Power10ConfigurationHash_Get(model),
                source_sha256=hashes, return_code=return_code,
                text_checks_passed=Power10TextPassed_Is(output, return_code),
                manual_acceptance_pending=True, critical_contract_review="NOT_PROVEN",
                policy="fprime_inspired_c; not NASA certification", functions=functions,
                 findings=findings, hard_failures=hard_failures, hard_findings=hard_findings, output=output)


def Power10Report_Save(root: Path, report: dict) -> None:
    WorkspacePolicy(root).Text_AtomicWrite(REPORT_PATH, json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def Power10Report_Load(root: Path) -> dict | None:
    try:
        report = json.loads(WorkspacePolicy(root).Path_Resolve(REPORT_PATH, allow_root=False).read_text(encoding="utf-8"))
        required = {"source_sha256": dict, "findings": list, "hard_failures": list,
                    "policy": str, "timestamp": str, "configuration_sha256": str}
        return report if (report.get("format_version") == 1 and
                          all(isinstance(report.get(key), kind) for key, kind in required.items()) and
                          all(isinstance(row, dict) for row in report["findings"])) else None
    except (OSError, ValueError, AttributeError):
        return None


def Power10Report_Current_Is(root: Path, model: ProjectModel, report: dict | None) -> bool:
    if not report or report.get("configuration_sha256") != Power10ConfigurationHash_Get(model):
        return False
    try:
        policy = WorkspacePolicy(root)
        hashes = report["source_sha256"]
        return (report["target_root"] == str(policy.root) and bool(hashes) and
                all(hashlib.sha256(policy.Path_Resolve(name, allow_root=False).read_bytes()).hexdigest() == digest
                    for name, digest in hashes.items()))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def Power10Report_Csv(report: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    columns = ("target", "function", "full_path", "file", "line", "code_lines", "reason")
    writer.writerow((*columns, "configuration_sha256", "source_sha256", "timestamp", "manual_acceptance_pending"))
    rows = list(report["findings"])
    rows.extend(report.get("hard_findings", ()))
    rows.extend(dict(reason=reason) for reason in report["hard_failures"])
    rows.append(dict(reason="critical_contract_review=NOT_PROVEN; manual acceptance pending; " + report["policy"]))
    for row in rows:
        writer.writerow((*(row.get(column, "") for column in columns), report["configuration_sha256"],
                         report["source_sha256"].get(row.get("file", ""), ""), report["timestamp"], True))
    return stream.getvalue()
