"""Normal current-source Flight generation; no case admission or old-project edits."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "apps/SCG/src"), str(ROOT / "apps/SCG/tests")]

from e19_project_fixture import E19Project_Create
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.generation_state import (
    ProjectGenerationState_Normalize,
    ProjectTargetGenerated_IsCurrent,
    TargetGenerationReceipt_Get,
)
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate

OUT = Path(__file__).resolve().parent


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            and p.suffix != ".pyc"}


def snapshot():
    result = {}
    for folder in ("apps/SCG/src", "apps/SCG/plugins", "contracts"):
        result.update({folder + "/" + name: value for name, value in hashes(ROOT / folder).items()})
    for path in (ROOT / "tools").glob("silverstar_mission_*.py"):
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("e19_project_fixture.py", "sx1278_project_fixture.py",
                 "ebyte_variant_fixture.py", "test_round2_targets.py"):
        path = ROOT / "apps/SCG/tests" / name
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("default", "e19"))
    args = parser.parse_args()
    label = "current-f" if args.case == "default" else "current-e19-c"
    output = ROOT / ".work/pf1117" / label
    inputs = ROOT / ".work/pf1117" / (label + "-inputs")
    receipt_path = OUT / (label + "-generation.json")
    if output.exists() or inputs.exists() or receipt_path.exists():
        raise ValueError("Only new inputs/output/receipt are permitted")
    before = snapshot()
    started = time.time()
    service = FccgService(ROOT / "apps/SCG")
    model = (ReferenceProject_Create("GuiConvergence_f4", catalog=service.catalog)
             if args.case == "default" else E19Project_Create(service.catalog, inputs))
    normalized_before = ProjectGenerationState_Normalize(model, "flight")
    model = service.ProjectConfiguration_Reconcile(model).model
    normalized_after = ProjectGenerationState_Normalize(model, "flight")
    validation = Project_Validate(model, service.catalog)
    if not validation.valid:
        raise ValueError(str(validation))
    input_hashes = hashes(inputs) if inputs.exists() else {}
    result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(
        inputs if inputs.exists() else ROOT / "apps/SCG"), output, TargetScope.FLIGHT)
    project = output / "Flight_Controller"
    saved = ProjectModel_Load(project / "SilverStar.ssproject")
    reopened = service.ProjectConfiguration_Reconcile(saved).model
    current = {"original_model": ProjectTargetGenerated_IsCurrent(model, service.catalog, project, "flight"),
               "saved_model": ProjectTargetGenerated_IsCurrent(saved, service.catalog, project, "flight"),
               "reopened_reconciled_model": ProjectTargetGenerated_IsCurrent(reopened, service.catalog, project, "flight")}
    after = snapshot()
    source_changed = sorted(n for n in before.keys() | after.keys() if before.get(n) != after.get(n))
    input_after = hashes(inputs) if inputs.exists() else {}
    old = ROOT / (".work/platform-finish-20261116/contracts/final-generated-e/f4/Flight_Controller"
                  if args.case == "default" else ".work/pf1117/contract-e19-b/Flight_Controller")
    source_files = hashes(project)
    old_files = {n: v for n, v in hashes(old).items() if not n.startswith(("build/", ".fccg/"))}
    changed = sorted(n for n in source_files.keys() | old_files.keys()
                     if not n.startswith(("build/", ".fccg/")) and source_files.get(n) != old_files.get(n))
    compiled_input = lambda n: Path(n).suffix.lower() in {".c", ".h", ".s", ".ld", ".mk"} or n == "Makefile"
    data = {"purpose": "Current-source normal generation and readiness; no hardware validation",
            "baseline_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "output": str(output), "project": str(project), "inputs": str(inputs),
            "targets": result.targets, "seconds": time.time() - started,
            "source_snapshot": before, "source_changed": source_changed,
            "synthetic_input_hashes": input_hashes, "synthetic_inputs_unchanged": input_after == input_hashes,
            "validation": asdict(validation), "configuration_reconcile_changed": normalized_before != normalized_after,
            "current": current, "saved_component_provenance": saved.component_provenance,
            "expected_current_receipt": TargetGenerationReceipt_Get(saved, service.catalog, "flight"),
            "generated_files": source_files, "old_project": str(old), "all_nonbuild_changed": changed,
            "compiled_source_changed": [n for n in changed if compiled_input(n)],
            "model": saved.Dictionary_Get()}
    with receipt_path.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
    print(label, "current", current, "source_changed", source_changed,
          "compiled_source_changed", data["compiled_source_changed"], flush=True)
    if source_changed or input_after != input_hashes or not all(current.values()):
        raise ValueError("Generation source drift, input mutation or stale readiness")


if __name__ == "__main__":
    main()
