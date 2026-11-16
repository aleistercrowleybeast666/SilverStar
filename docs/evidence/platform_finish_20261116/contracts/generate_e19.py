"""Normally generate an isolated E19 software fixture, without case admission."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "apps/SCG/src"), str(ROOT / "apps/SCG/tests")]

from e19_project_fixture import E19Project_Create
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope


def snapshot():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ("apps/SCG/src", "apps/SCG/plugins", "contracts")
            for path in (ROOT / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=("a", "b"))
    args = parser.parse_args()
    work = ROOT / ".work/pf1117"
    inputs = work / ("contract-e19-input-" + args.label)
    output = work / ("contract-e19-" + args.label)
    receipt = ROOT / ".work/platform-finish-20261116/contracts" / ("e19-generation-" + args.label + ".json")
    if inputs.exists() or output.exists() or receipt.exists():
        raise ValueError("Fresh inputs/output/receipt required; no previous evidence is overwritten")
    before = snapshot()
    started = time.time()
    service = FccgService(ROOT / "apps/SCG")
    model = E19Project_Create(service.catalog, inputs)
    input_hashes = {path.relative_to(inputs).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in inputs.rglob("*") if path.is_file()}
    result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(inputs), output, TargetScope.ALL)
    changed = [name for name, digest in input_hashes.items()
               if hashlib.sha256((inputs / name).read_bytes()).hexdigest() != digest]
    after = snapshot()
    source_changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    data = {"purpose": "Final-identity E19 synthetic wiring; no hardware test or case admission",
            "owner": "/root/silverstar_finish/platform-finish-20261116/contracts",
            "baseline_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "output": str(output), "inputs": str(inputs), "targets": result.targets,
            "seconds": time.time() - started, "model": model.Dictionary_Get(),
            "input_hashes": input_hashes, "input_changed": changed,
            "generation_source_before": before, "source_changed": source_changed,
            "output_hashes": {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in output.rglob("*") if path.is_file()}}
    receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf8")
    if changed or source_changed:
        raise ValueError("Input/source changed during generation")
    print(args.label, result.targets, len(result.file_hashes), "changed=[]", flush=True)


if __name__ == "__main__":
    main()
