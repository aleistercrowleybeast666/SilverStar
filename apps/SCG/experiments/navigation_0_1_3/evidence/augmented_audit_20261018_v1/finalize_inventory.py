"""Verify unchanged inputs and inventory retained review evidence; no cleanup."""
from pathlib import Path
import hashlib
import json

OUTPUT = Path(__file__).resolve().parent
HERE = OUTPUT.parents[1]
ROOT = HERE.parents[3]


def Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    focused = json.loads((OUTPUT / "independent_run.json").read_text(encoding="utf-8"))
    full_dir = HERE / "evidence/augmented_audit_20261018_full"
    full = json.loads((full_dir / "run.json").read_text(encoding="utf-8"))
    incoming = json.loads((HERE / "evidence/inekf20_20261018_run01/run.json").read_text(encoding="utf-8"))
    assert focused["exit_code"] == full["exit_code"] == 0
    assert not focused["changed_during_run"] and not full["changed_during_run"]
    for name, digest in focused["source_sha256_before"].items():
        assert Hash_Get(ROOT / name) == digest
    for path in HERE.glob("*.py"):
        key = path.relative_to(ROOT).as_posix()
        assert Hash_Get(path) == incoming["source_sha256_after"][key] == full["source_sha256_after"][key]
    historical = []
    for inventory_path in sorted((HERE / "evidence").glob("*/inventory.json")):
        if inventory_path.parent == full_dir:
            continue
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        for entry in inventory["retained_evidence"]:
            assert Hash_Get(ROOT / entry["path"]) == entry["sha256"]
            historical.append(entry["path"])
    files = sorted(p for directory in (OUTPUT, full_dir) for p in directory.iterdir() if p.is_file())
    entries = [dict(path=p.relative_to(ROOT).as_posix(), sha256=Hash_Get(p), bytes=p.stat().st_size) for p in files]
    record = dict(owner="navigation_0_1_3 independent augmented-model audit",
        purpose="retained independent mathematical review and fresh unchanged full-suite execution",
        findings="No substantive implementation defect found; no existing source/test/document edits",
        focused_result="five targeted checks PASS", full_result="250 passed, zero failed/skipped; 13.77 s",
        existing_inputs_unchanged=True, python_sources_match_incoming_250_pass_revision=True,
        historical_artifact_hashes_verified=historical, retained_evidence=entries,
        new_evidence_bytes_excluding_this_inventory=sum(item["bytes"] for item in entries),
        report_timing="REVIEW.md and this final inventory were written after both checks; executed hashes verified",
        cleanup="None. Retained evidence; no deletion authorization.", self_hash="omitted to avoid self-reference")
    with (OUTPUT / "final_inventory.json").open("x", encoding="utf-8") as file:
        file.write(json.dumps(record, indent=2) + "\n")
    print(json.dumps(dict(existing_inputs_unchanged=True, prior_artifacts_verified=len(historical),
        new_evidence_bytes=record["new_evidence_bytes_excluding_this_inventory"],
        inventory=str(OUTPUT / "final_inventory.json"))))
