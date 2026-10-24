"""Retain audit hashes/diff; never delete, overwrite evidence, or run adapters."""
from pathlib import Path
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parents[3]
OUTPUT = Path(__file__).resolve().parent


def Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Inventory_Create():
    final = json.loads((HERE / "evidence/audit_20261018_final/run.json").read_text(encoding="utf-8"))
    assert final["exit_code"] == 0 and not final["changed_during_run"]
    code = [p for p in HERE.iterdir() if p.suffix == ".py" or p.name == "pytest.ini"]
    for path in code:
        assert Hash_Get(path) == final["source_sha256_after"][path.relative_to(ROOT).as_posix()]
    original = json.loads((HERE / "evidence/eskf20_run02/run.json").read_text(encoding="utf-8"))
    for name in ("test_mathematics.py", "test_eskf20.py", "test_isolation.py", "pytest.ini"):
        path = HERE / name
        assert Hash_Get(path) == original["source_sha256_after"][path.relative_to(ROOT).as_posix()]
    historical = []
    for name in ("run01", "run02", "run03", "eskf20_run01", "eskf20_run02"):
        inventory = json.loads((HERE / "evidence" / name / "inventory.json").read_text(encoding="utf-8"))
        for entry in inventory["retained_evidence"]:
            assert Hash_Get(ROOT / entry["path"]) == entry["sha256"]
            historical.append(entry["path"])
    initial = json.loads((OUTPUT / "inventory_initial.json").read_text(encoding="utf-8"))
    for entry in initial["files"]:
        assert Hash_Get(ROOT / entry["retained_path"]) == entry["sha256"]
    changed = ["lie_group.py", "inekf_reference.py", "eskf20_reference.py", "verify.py",
               "README.md", "ESKF20_MODEL.md", "test_independent_audit.py"]
    patch = []
    for name in changed:
        prior = OUTPUT / "baseline" / name
        before = prior.read_text(encoding="utf-8").splitlines(keepends=True) if prior.exists() else []
        after = (HERE / name).read_text(encoding="utf-8").splitlines(keepends=True)
        patch.extend(difflib.unified_diff(before, after, fromfile="before/" + name,
                                         tofile="after/" + name))
    with (OUTPUT / "audit_changes.patch").open("x", encoding="utf-8", newline="\n") as file:
        file.write("".join(patch))
    sources = [HERE / name for name in changed + ["INDEPENDENT_AUDIT_20261018.md"]]
    evidence = sorted(p for p in (HERE / "evidence").glob("audit_20261018*/**/*") if p.is_file())
    def Entry(path):
        return dict(path=path.relative_to(ROOT).as_posix(), sha256=Hash_Get(path), bytes=path.stat().st_size)
    size = sum(path.stat().st_size for path in evidence)
    assert size < 2_000_000
    report = dict(owner="navigation_0_1_3 independent mathematical audit",
        purpose="retained pre-fix counterexamples, source snapshots, patches and final host validation",
        source_commit=final["source_commit"], scope="offline synthetic mathematics and existing metadata isolation",
        final_run="evidence/audit_20261018_final/run.json", final_pytest_result="163 passed, zero failed/skipped",
        code_matches_final_executed_hashes=True, existing_120_tests_and_configuration_unchanged=True,
        historical_artifact_hashes_verified=historical, baseline_hashes_verified=True,
        final_sources=[Entry(path) for path in sources], retained_evidence=[Entry(path) for path in evidence],
        audit_evidence_bytes_excluding_this_inventory=size,
        report_timing="Audit report, patch and final inventory written after final tests; code/test hashes verified unchanged.",
        cleanup="None; all listed files are retained evidence or source. No deletion authorization.",
        self_hash="omitted to avoid recursive self-reference")
    with (OUTPUT / "final_inventory.json").open("x", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(final_result=report["final_pytest_result"],
        code_hashes_match=True, historical_artifacts_verified=len(historical),
        retained_bytes=size, inventory=str(OUTPUT / "final_inventory.json"))))


if __name__ == "__main__":
    Inventory_Create()
