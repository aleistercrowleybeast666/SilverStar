"""Compare actual current builds with preserved old artifacts and consume strict reports."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/SCG/src"))

from generate_current import snapshot
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.artifact_stack import (
    ArtifactStackReportSummary_Decode,
    ArtifactStackReportSummary_Encode,
)
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.model import ProjectModel_Load

OUT = Path(__file__).resolve().parent


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    service = FccgService(ROOT / "apps/SCG")
    records = []
    for label, old_name in (("current-f", "final-artifact-summary.json"),
                            ("current-e19-c", "e19-final-artifact-summary.json")):
        generation_path = OUT / (label + "-generation.json")
        generated = json.loads(generation_path.read_bytes())
        project = Path(generated["project"])
        commands_path = OUT / (label + "-build") / "commands.json"
        commands = json.loads(commands_path.read_bytes())
        expected_gates = {(c, g) for c in ("Release", "Debug")
                          for g in ("all", "artifact-check", "stack-report")}
        if (len(commands) != 6 or {(c["configuration"], c["gate"]) for c in commands} != expected_gates
                or any(c["exit"] != 0 for c in commands)):
            raise ValueError("The six actual gates did not all complete successfully: " + label)
        stability = json.loads((commands_path.parent / "input-stability.json").read_bytes())
        if stability["changed"]:
            raise ValueError("Build inputs changed: " + label)
        old_summary_path = OUT.parent / "contracts/runs" / old_name
        old_summary = json.loads(old_summary_path.read_bytes())
        archive_label = "f407-default-e-20261117" if label == "current-f" else "f407-e19-b-20261117"
        archive_inventory_path = ROOT / "dist/pf1117-evidence" / archive_label / "FILE_INVENTORY.json"
        archive_inventory = json.loads(archive_inventory_path.read_bytes())["files"]
        configurations = {}
        for config in ("Release", "Debug"):
            build = project / "build/FCCG/SilverStar_F407" / config
            expected = old_summary["configurations"][config]["artifact_hashes"]
            actual = {name: file_hash(build / name) for name in expected}
            changed = [name for name in expected if actual[name] != expected[name]]
            prefix = "build/FCCG/SilverStar_F407/" + config + "/"
            suffixes = {".o", ".su", ".d", ".s", ".elf", ".bin", ".hex", ".map"}
            archived_outputs = {n.removeprefix(prefix): v["sha256"] for n, v in archive_inventory.items()
                                if n.startswith(prefix) and Path(n).suffix in suffixes}
            current_outputs = {f.relative_to(build).as_posix(): file_hash(f) for f in build.rglob("*")
                               if f.is_file() and f.suffix in suffixes}
            all_output_changes = sorted(n for n in current_outputs.keys() | archived_outputs.keys()
                                        if current_outputs.get(n) != archived_outputs.get(n))
            report_path = build / "stack-budget.json"
            report = json.loads(report_path.read_bytes())
            summary = ArtifactStackReportSummary_Encode("FIRMWARE_STACK_REPORT|" + str(report_path), project)
            decoded = ArtifactStackReportSummary_Decode(summary)
            if not decoded or not decoded["passes"]:
                raise ValueError("Current application rejected the strict report: " + label + config)
            configurations[config] = {
                "compiled_artifact_count": len(actual), "compiled_artifacts_sha256": actual,
                "changed_from_preserved_epoch": changed, "stack_report_sha256": file_hash(report_path),
                "all_compiled_output_count_including_bin_hex": len(current_outputs),
                "all_compiled_output_hashes": current_outputs,
                "all_compiled_output_changes": all_output_changes,
                "current_application_consumes_report": True,
                "software_review": report["software_review"],
                "whole_program_stack_acceptance": report["whole_program_stack_acceptance"],
                "main_msp_exceptions": report["main_msp_exceptions"],
                "tasks": report["tasks"],
            }
            if changed or all_output_changes:
                raise ValueError("Actual compiled artifact changed: " + label + config + str(changed))
        saved = ProjectModel_Load(project / "SilverStar.ssproject")
        reopened = service.ProjectConfiguration_Reconcile(saved).model
        current = {"saved": ProjectTargetGenerated_IsCurrent(saved, service.catalog, project, "flight"),
                   "reopened_reconciled": ProjectTargetGenerated_IsCurrent(reopened, service.catalog, project, "flight")}
        now = snapshot()
        source_changed = sorted(n for n in now.keys() | generated["source_snapshot"].keys()
                                if now.get(n) != generated["source_snapshot"].get(n))
        record = {"label": label, "project": str(project),
                  "generation_receipt_sha256": file_hash(generation_path),
                  "commands_sha256": file_hash(commands_path), "commands": commands,
                  "old_artifact_summary": str(old_summary_path),
                  "old_artifact_summary_sha256": file_hash(old_summary_path),
                  "protected_archive_inventory_sha256": file_hash(archive_inventory_path),
                  "compiled_source_changed": generated["compiled_source_changed"],
                  "nonbuild_changes": generated["all_nonbuild_changed"],
                  "configurations": configurations, "current_after_build": current,
                  "source_changed_since_generation": source_changed,
                  "hardware_tested": False, "gui_mouse_test_performed": False}
        records.append(record)
        if source_changed or not all(current.values()):
            raise ValueError("Current source/readiness drift: " + label)
        print(label, "six gates PASS, actual artifacts unchanged, application report/current PASS", flush=True)
    with (OUT / "CURRENT_RECEIPT.json").open("x", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps({"projects": records, "case_admissions_added": 0,
                                "old_protected_archives_modified": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
