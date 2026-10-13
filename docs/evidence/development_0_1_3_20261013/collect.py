"""Collect root integration evidence; reads existing results, never reruns tests."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    selected = ROOT / ".work/dev013_integration/scg-selected-final.log"
    single = ROOT / ".work/dev013_integration/scg-ui-fixed.log"
    if "52 passed, 4 skipped" not in selected.read_text(encoding="utf-8"):
        raise RuntimeError("The complete SCG selection run has not passed")
    if "1 passed" not in single.read_text(encoding="utf-8"):
        raise RuntimeError("The focused UI regression has not passed")
    expected_tag = "942f20ef64df3cb1aa65be7349361c409418aa0f"
    if git("rev-parse", "v0.1.2") != expected_tag:
        raise RuntimeError("Frozen release tag changed")
    protected_changes = git("diff", "c31c13c", "--name-only", "--",
                            "apps/FLP", "docs/public/releases")
    if protected_changes:
        raise RuntimeError("Unexpected FLP/release-document change")
    component = "apps/SCG/src/silverstar_fccg/ui/pages/components.py"
    if git("diff", "c31c13c", "--", component):
        raise RuntimeError("The baseline UI comparison is no longer valid")
    firmware = ROOT / "apps/SCG/docs/evidence/log_file_service_20261013"
    bound = json.loads((firmware / "source_snapshot.sha256.json").read_text())
    for name, expected in bound.items():
        if sha(ROOT / name) != expected:
            raise RuntimeError("Firmware source changed: " + name)
    artifacts = json.loads((firmware / "runs/lf13final5/artifacts.sha256.json").read_text())
    checked_artifacts = {}
    for name, record in artifacts.items():
        if Path(name).suffix in {".elf", ".bin", ".hex", ".map"}:
            if sha(ROOT / ".work/lf13final5" / name) != record["sha256"]:
                raise RuntimeError("Firmware artifact changed: " + name)
            checked_artifacts[name] = record
    windows_name = "apps/GSHC/docs/evidence/windows_log_transfer_20261013.zip"
    windows_archive = ROOT / windows_name
    windows_hash = "281984668d74769306c198d9d36dcfc8685062d715b437e2517341f8c608fe05"
    if sha(windows_archive) != windows_hash:
        raise RuntimeError("Sealed Windows evidence archive changed")
    with zipfile.ZipFile(windows_archive) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Windows evidence archive CRC mismatch")
        inventory = json.loads(archive.read("inventory.json"))["entry_sha256"]
        if set(inventory) != set(archive.namelist()) - {"inventory.json"}:
            raise RuntimeError("Windows evidence inventory coverage mismatch")
        for name, expected in inventory.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise RuntimeError("Windows evidence entry changed: " + name)
        windows_sources = json.loads(archive.read("v7/verification.json"))["dirty_source_sha256"]
        for name, expected in windows_sources.items():
            if sha(ROOT / name) != expected:
                raise RuntimeError("Windows source changed: " + name)
            if archive.read("source_snapshot/" + name) != (ROOT / name).read_bytes():
                raise RuntimeError("Windows source snapshot mismatch: " + name)
    test = "apps/SCG/tests/test_optional_protocols.py"
    for name, destination in ((test, "baseline_test_optional_protocols.py"),
                              (component, "baseline_components.py")):
        content = subprocess.check_output(["git", "show", "c31c13c:" + name], cwd=ROOT)
        (OUTPUT / destination).write_bytes(content)
    shutil.copyfile(ROOT / test, OUTPUT / "tested_optional_protocols.py")
    shutil.copyfile(selected, OUTPUT / selected.name)
    shutil.copyfile(single, OUTPUT / single.name)
    records = {
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "head_before_integration_evidence_commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "frozen_tag": expected_tag,
        "frozen_commit": git("rev-parse", "v0.1.2^{commit}"),
        "python": sys.version,
        "executable": sys.executable,
        "git_version": git("--version"),
        "versions": {name: importlib.metadata.version(name)
                     for name in ("pytest", "PySide6", "jsonschema", "pyserial")},
        "tests": [
            {"command": ".venv/Scripts/python.exe -m pytest apps/SCG/tests/test_optional_protocols.py::test_protocol_combos_and_logging_disabled_state_are_stable -q --basetemp=apps/SCG/.work/dev013-ui-fix",
             "exit_code": 0, "result": "1 passed", "log": single.name},
            {"command": ".venv/Scripts/python.exe -m pytest apps/SCG/tests/test_optional_protocols.py apps/SCG/tests/test_architecture_maintenance_selection.py apps/SCG/tests/test_storage_binding_admission.py -q --basetemp=apps/SCG/.work/dev013-selection",
             "exit_code": 0, "result": "52 passed, 4 expected skips", "log": selected.name}],
        "test_environment": {"PYTHONPATH": str(ROOT / "apps/SCG/src"),
                             "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf8",
                             "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"},
        "changed_test_sha256": sha(ROOT / test),
        "unchanged_baseline_ui_source": component,
        "firmware_source_bindings_rechecked": bound,
        "firmware_artifacts_rechecked": checked_artifacts,
        "windows_evidence_rechecked": {
            "path": windows_name, "sha256": windows_hash,
            "bytes": windows_archive.stat().st_size,
            "hashed_entries": len(inventory), "crc": "PASS",
            "current_sources_match_final_v7_snapshot": windows_sources,
        },
        "aggregate_safety_acceptance": "BLOCKED: strict stack FAIL and documented NOT PROVEN items remain",
        "hardware_access": "none",
    }
    records["retained_file_sha256"] = {
        str(path.relative_to(OUTPUT)): sha(path) for path in OUTPUT.iterdir()
        if path.is_file() and path.name != "verification.json"
    }
    (OUTPUT / "verification.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Root integration evidence collected; firmware safety acceptance remains blocked.")


if __name__ == "__main__":
    main()
