"""Freeze explicit validation scopes, including failures; never synthesize a suite."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/FCCG/auto_memory_layout_20261002"
OUT = DOC / "final_evidence"
OUT.mkdir(exist_ok=False)
(OUT / ".gitattributes").write_text("* -text\n")
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

v6 = json.loads((DOC / "evidence_v6/results.json").read_text())
v8 = json.loads((DOC / "evidence_v8/results.json").read_text())
assert len(v6["stages"]) == 29
assert [(s["name"], s["exit_code"]) for s in v6["stages"] if s["exit_code"] != 0] == [("SF6_host-tests", 2)]
assert all(s["exit_code"] == 0 for s in v8["results"])
assert all(s["exit_code"] == 0 for s in json.loads((DOC / "uart_final_audits_v2/results.json").read_text())["results"])
report = {
    "utc": datetime.now(timezone.utc).isoformat(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "authorized_base": "fd0a71c2f78d86dd1d0b281ca04863b42df5ad1a",
    "full_compilation_scope": "v6 generated inputs at b6309c8: nine Release ARM layouts, four real ARM -fanalyzer builds/links, all four architecture/PoT/stack reports; SF6 Host failed its old covariance assumption",
    "incremental_scope": "v8 four fresh links from exact v6 Release objects, current fail-closed tool, four artifact/architecture/PoT/stack checks and corrected complete SF6 Host; latest UART uniqueness auditor rechecked all four exact ELF files",
    "fresh_generation_scope": json.loads((DOC / "evidence_v10/fresh_generation_runtime_compare.json").read_text()),
    "not_proven": ["useful assertion semantics and complete critical-contract manual acceptance", "complete stack bounds including all task/library/indirect/dynamic/main/MSP/ISR paths", "STM32 WCET and memory-bus timing", "hardware/flight qualification", "integration with the parent's later SF6 revision"],
    "hardware_access": False,
    "v6_source_unchanged_after": v6["source_unchanged_after"],
    "v6_source_change_reason": "owning Host tests/tools were corrected while immutable generated v6 inputs remained unchanged; fresh v10 runtime C/H/S/ld comparison is byte-identical",
    "v6_stages": v6["stages"], "v8_stages": v8["results"], "resources": {}, "artifact_sha256": {},
    "archived_files_sha256": {},
}
tracked = subprocess.check_output(["git", "ls-files", "apps/FCCG"], cwd=ROOT, text=True).splitlines()
report["fccg_source_sha256"] = {name: sha(ROOT / name) for name in tracked}
tool = ROOT / "apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/auto_memory_layout.py"
source = tool.read_text(); lines = source.splitlines(keepends=True)
bodies = []
for node in ast.parse(source).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("Regions_Parse", "SourceOwners_Check", "Score_Get", "LinkedGroups_Check", "LayoutCandidates_Link", "Layout_Link"):
        bodies.append("".join(lines[node.lineno - 1:node.end_lineno]) + "\n\n")
bodies.append(subprocess.check_output(["git", "diff", report["authorized_base"], "--", "apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_firmware_artifact.ps1"], cwd=ROOT, text=True))
(OUT / "review-critical-final.txt").write_text("".join(bodies))
archive = OUT / "sources_artifacts_logs.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as packed:
    def add(path, label):
        packed.write(path, label); report["archived_files_sha256"][label] = sha(path)
    # Exact repository source bytes, in addition to the commit and per-file hashes.
    for name in tracked:
        add(ROOT / name, "repository_source/" + name)
    for directory in sorted(DOC.iterdir()):
        if directory.is_dir() and (directory.name.startswith("evidence_") or directory.name.startswith("catalog_fault_") or directory.name.startswith("uart_")):
            for path in directory.rglob("*"):
                if path.is_file(): add(path, "run_evidence/" + path.relative_to(DOC).as_posix())
    for path in DOC.glob("tests_*.log"):
        add(path, "regressions/" + path.name)
    for path in DOC.glob("*.py"):
        add(path, "drivers/" + path.name)
    add(Path(__file__), "drivers/freeze_memory_final.py")
    add(OUT / "review-critical-final.txt", "review-critical-final.txt")
    for name in ("PureINS", "KF6", "ESKF15", "SF6"):
        original = ROOT / ".work/AutoMemoryCandidates_v6" / name / "Flight_Controller"
        current = ROOT / ".work/AutoMemoryCandidates_v8" / name / "Flight_Controller"
        # Preserve generated inputs, licenses, decoder packages and test source.
        for version, project in (("v6", original), ("v8", current)):
            for path in project.rglob("*"):
                if path.is_file() and "build" not in path.relative_to(project).parts and "__pycache__" not in path.relative_to(project).parts:
                    add(path, "project_inputs/" + version + "/" + name + "/" + path.relative_to(project).as_posix())
        for version, project in (("v6", original), ("v8", current)):
            for path in (project / "build/FCCG").rglob("*"):
                if path.is_file() and (path.suffix in (".elf", ".map", ".bin", ".hex", ".su") or path.name in ("decision.json", "stack-budget.json")):
                    label = "linked_artifacts/" + version + "/" + name + "/" + path.relative_to(project).as_posix()
                    add(path, label)
                    report["artifact_sha256"][label] = sha(path)
        decision = json.loads((current / "build/FCCG/SilverStar_F407/Release/auto/memory_layout/decision.json").read_text())
        original_decision = json.loads((original / "build/FCCG/SilverStar_F407/Release/auto/memory_layout/decision.json").read_text())
        assert decision["object_sha256"] == original_decision["object_sha256"]
        for relative, digest in decision["object_sha256"].items():
            assert sha(current / relative) == digest == sha(original / relative)
            add(current / relative, "compiled_objects/" + name + "/" + relative)
        report["resources"][name] = {"final_decision": decision, "original_elf_sha256": original_decision["elf_sha256"],
                                   "same_elf_as_v6": decision["elf_sha256"] == original_decision["elf_sha256"],
                                   "resource_audit": v8[name]["existing_resource_audit"], "audit_errors": v8[name]["audit_errors"]}
    # Preserve pre-fix leaked synthetic ELF plus post-fix failure logs, explicitly
    # classified as rejected test artifacts rather than firmware candidates.
    for path in (ROOT / ".work/pytest_memory_review_v1").rglob("*"):
        if path.is_file() and (path.suffix in (".elf", ".log", ".ld", ".json") or path.name == "failure.log"):
            add(path, "REJECTED_synthetic_fault_cases/" + path.relative_to(ROOT / ".work/pytest_memory_review_v1").as_posix())
report["archive_sha256"] = sha(archive)
report["fccg_sources_unchanged_after_capture"] = all(sha(ROOT / name) == value for name, value in report["fccg_source_sha256"].items())
(OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": report["archive_sha256"],
                  "source_commit": report["source_commit"], "source_unchanged": report["fccg_sources_unchanged_after_capture"]}, indent=2))
