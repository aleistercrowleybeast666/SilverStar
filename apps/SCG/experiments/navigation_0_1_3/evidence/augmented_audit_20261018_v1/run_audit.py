"""Record the focused audit without overwriting any prior run or source file."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

OUTPUT = Path(__file__).resolve().parent
HERE = OUTPUT.parents[1]
ROOT = HERE.parents[3]


def Snapshot_Get():
    files = sorted([p for p in HERE.iterdir() if p.is_file()] + list(OUTPUT.glob("*.py")))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


if __name__ == "__main__":
    command = [sys.executable, "-B", "-W", "error", str(OUTPUT / "check_independent.py")]
    overrides = dict(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
                     OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    before = Snapshot_Get()
    started = datetime.now(timezone.utc).isoformat()
    run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, **overrides),
        capture_output=True, encoding="utf-8", errors="strict", timeout=120)
    after = Snapshot_Get()
    with (OUTPUT / "independent.log").open("x", encoding="utf-8") as file:
        file.write(run.stdout + run.stderr)
    record = dict(owner="navigation_0_1_3 independent augmented-model audit",
        purpose="retained physical counterchecks; no production or adapter execution",
        command=command, cwd=str(ROOT), started_utc=started, exit_code=run.returncode,
        python=sys.version, versions={p: importlib.metadata.version(p) for p in ("numpy", "scipy", "pytest")},
        environment_overrides=overrides,
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        source_sha256_before=before, source_sha256_after=after,
        changed_during_run=[p for p in set(before) | set(after) if before.get(p) != after.get(p)],
        log_sha256=hashlib.sha256((OUTPUT / "independent.log").read_bytes()).hexdigest(),
        cleanup="None. Retained evidence and source; not a cleanup target.")
    with (OUTPUT / "independent_run.json").open("x", encoding="utf-8") as file:
        file.write(json.dumps(record, indent=2) + "\n")
    print(run.stdout + run.stderr)
    raise SystemExit(run.returncode)
