"""Seal or verify publishable evidence bytes, without interpreting test results."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = HERE / "EVIDENCE_SHA256.json"


def Files_Get() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z",
         "--", HERE.relative_to(ROOT).as_posix()], cwd=ROOT,
    )
    paths = {ROOT / item.decode("utf-8") for item in output.split(b"\0") if item}
    return sorted(path for path in paths if path != MANIFEST and path.is_file())


def Snapshot_Get() -> dict[str, dict[str, str | int]]:
    result = {}
    for path in Files_Get():
        data = path.read_bytes()
        result[path.relative_to(HERE).as_posix()] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
    return result


def Main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "verify"))
    args = parser.parse_args()
    current = Snapshot_Get()
    if args.action == "seal":
        if MANIFEST.exists():
            raise FileExistsError("Preserve the prior manifest; do not overwrite evidence")
        manifest = {
            "scope": "Exact publishable evidence bytes; not a claim that all recorded gates pass",
            "source_head_before_evidence_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            ).strip(),
            "files": current,
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    else:
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        changed = sorted(key for key in current.keys() | expected.keys()
                         if current.get(key) != expected.get(key))
        if changed:
            print(json.dumps({"changed_missing_or_unrecorded": changed}, indent=2))
            return 1
    print(json.dumps({"files": len(current), "bytes": sum(v["bytes"] for v in current.values()),
                      "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                      "action": args.action, "exit_code": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
