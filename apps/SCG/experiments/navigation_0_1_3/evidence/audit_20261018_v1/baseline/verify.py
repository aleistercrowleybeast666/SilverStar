"""Run only this experiment and retain small, non-overwriting evidence; no cleanup."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SCG = ROOT / "apps/SCG"


def Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Snapshot_Get():
    files = [p for p in HERE.iterdir() if p.is_file()]
    files += list((SCG / "src").rglob("*.py"))
    files += [ROOT / "apps/FLP/src/silverstar_flp/plugins/algorithms/eskf15/filter.py"]
    # Declarative catalog inputs only; do not read/execute device C payloads.
    for directory in (SCG / "plugins/builtin", SCG / "plugins/installed"):
        if directory.exists():
            files += list(directory.rglob("*.json"))
    return {p.relative_to(ROOT).as_posix(): Hash_Get(p) for p in sorted(set(files))}


def Git_Read(*args):
    run = subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr)
    return run.stdout.strip()


def Verification_Run():
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name):
        raise SystemExit("Usage: python -B verify.py <new-run-name>")
    output = HERE / "evidence" / name
    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-B", "-m", "pytest", "-c", str(HERE / "pytest.ini"),
               "-v", str(HERE / "test_mathematics.py"), str(HERE / "test_isolation.py"),
               str(HERE / "test_eskf20.py")]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    before = Snapshot_Get()
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    run = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=180)
    after = Snapshot_Get()
    log = output / "pytest.log"
    log.write_text(run.stdout + run.stderr, encoding="utf-8")
    record = dict(owner="navigation_0_1_3 InEKF and ESKF20 experiments", purpose="retained host mathematical/isolation evidence",
                  started_utc=started, elapsed_s=time.monotonic()-clock, command=command, cwd=str(ROOT),
                  exit_code=run.returncode, python=sys.version, executable=sys.executable,
                  versions={p: importlib.metadata.version(p) for p in ("numpy", "scipy", "pytest")},
                  environment_overrides={k: environment[k] for k in ("PYTHONDONTWRITEBYTECODE",
                      "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")},
                  source_commit=Git_Read("rev-parse", "HEAD"),
                  dirty_status=Git_Read("status", "--short", "--untracked-files=no"),
                  source_sha256_before=before, source_sha256_after=after,
                  changed_during_run=[p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)],
                  log_sha256=Hash_Get(log), scope="host float64 synthetic mathematics and read-only catalog isolation",
                  not_run=["GNSS/M9N adapter regressions", "production test suites", "Power of Ten",
                           "C static analyzer", "ARM compile/link", "hardware or flight tests"],
                  cleanup="None. Source and retained evidence are not cleanup targets.")
    report = output / "run.json"
    report.write_text(json.dumps(record, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    inventory = dict(owner=record["owner"], purpose=record["purpose"], retained_evidence=[
        dict(path=p.relative_to(ROOT).as_posix(), sha256=Hash_Get(p), bytes=p.stat().st_size)
        for p in (log, report)], inventory_self_hash="omitted to avoid recursive self-reference")
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2)+"\n", encoding="utf-8")
    print(run.stdout + run.stderr)
    print(f"Evidence: {output}")
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(Verification_Run())
