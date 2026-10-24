"""Small retained evidence runner; refuses overwrite; no hardware/production imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy
import scipy
import pytest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
TASK = REPO/".work"/"dev013_installation_calibration_20261018"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--flat", action="store_true", help="new prefixed files in existing task directory; no new directory")
    args = parser.parse_args()
    if not args.run.isascii() or not args.run.isalnum() or len(args.run) > 32:
        parser.error("run must be a short ASCII alphanumeric name")
    target = (TASK/args.run).resolve()
    if not target.is_relative_to(TASK.resolve()):
        parser.error("evidence path outside task")
    source_files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".ini", ".md")]
    snapshot_hashes = {p.name: digest(p) for p in source_files}
    if args.flat:
        if target.exists() or any(TASK.glob(args.run+"_*")):
            parser.error("run evidence already exists")
        source = {p.name: {"bytes_hex": p.read_bytes().hex(), "sha256": snapshot_hashes[p.name]} for p in source_files}
        source_path = TASK/(args.run+"_source.json")
        source_path.write_text(json.dumps(source, indent=2, ensure_ascii=True)+"\n", encoding="utf-8")
        path_for = lambda name: TASK/(args.run+"_"+name)
    else:
        target.mkdir(parents=True, exist_ok=False)
        source = target/"source"; source.mkdir()
        for path in source_files: shutil.copyfile(path, source/path.name)
        source_path = source
        path_for = lambda name: target/name
    command = [sys.executable, "-B", "-m", "pytest", "-c", str(ROOT/"pytest.ini"), str(ROOT), "-q", "-W", "error"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", INSTALL_CAL_EVIDENCE=str(TASK if args.flat else target),
               INSTALL_CAL_PREFIX=args.run+"_" if args.flat else "")
    started = datetime.now(timezone.utc).isoformat(); begin = time.monotonic()
    with path_for("pytest.log").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124; log.write("\nRUNNER_TIMEOUT_240_SECONDS\n")
    if any(digest(p) != snapshot_hashes[p.name] for p in source_files):
        code = 125
        with path_for("pytest.log").open("a", encoding="utf-8") as log: log.write("\nSOURCE_CHANGED_DURING_RUN\n")
    metadata = {"owner": "installation_calibration_B0_B2a", "purpose": "offline synthetic validation, not hardware", "started_utc": started,
        "command": command, "cwd": str(REPO), "exit_code": code, "elapsed_seconds": time.monotonic()-begin,
        "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
        "numpy": numpy.__version__, "scipy": scipy.__version__, "pytest": pytest.__version__,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "scope": "only this experiment; no production gates or hardware tests", "source_snapshot": str(source_path.relative_to(REPO)),
        "source_hashes": snapshot_hashes, "source_snapshot_format": "exact_bytes_hex" if args.flat else "files"}
    path_for("results.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
    outputs = [p for p in (TASK.glob(args.run+"_*") if args.flat else target.rglob("*")) if p.is_file()]
    inventory = [{"path": str(p.relative_to(REPO)), "bytes": p.stat().st_size, "sha256": digest(p),
                  "owner": metadata["owner"], "purpose": "retained test evidence", "cleanup_authorized": False}
                 for p in outputs]
    path_for("inventory.json").write_text(json.dumps(inventory, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"run": str(path_for("results.json") if args.flat else target), "exit_code": code, "seconds": metadata["elapsed_seconds"],
                      "retained_bytes": sum(x["bytes"] for x in inventory)}, indent=2))
    print(path_for("pytest.log").read_text(encoding="utf-8"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
