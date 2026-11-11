"""Hash the declared FLP software inputs and current FLP source without changing them."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess

TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='full')
tag = parser.parse_args().tag


def entry(path):
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest()}


tracked = subprocess.check_output(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "apps/FLP"],
    cwd=ROOT, text=True).splitlines()
sources = [entry(ROOT / name) for name in tracked if (ROOT / name).is_file()]
paths = set()
for suffix in ("*.ssdecoder", "*.ssproject", "*.sslog"):
    paths.update((TASK / "inputs").rglob(suffix))
for pattern in ("*.json", "*.jsonl", "*.sslog", "*/compile.json", "*/receipt.json"):
    paths.update((TASK / "producers").glob(pattern))
base = ROOT / ".work/gui-convergence-20261110"
for name in ("horizon-traces-final", "native-horizon-traces"):
    for pattern in ("*backend_horizon*/*.frames", "*backend_horizon*/compile.json"):
        paths.update((base / name).glob(pattern))
for name in ("native-horizon", "horizon-traces-final"):
    paths.update((base / name).rglob("*.ssdecoder"))
    paths.update((base / name).rglob("project_algorithm_parameters.h"))
payload = dict(
    source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         text=True).strip(),
    scope="Fresh synthetic CPU inputs only; raw captured hardware inputs remain unavailable.",
    source_files=sources,
    input_files=[entry(path) for path in sorted(paths) if path.is_file()],
    timing_scopes={
        "existing/imported": "normal generated KF6 current mode0",
        "eskf": "normal generated ESKF15 current mode0",
        "joint/eskf-replay/aggregation-*": "separate normal generated mode1 replay inputs",
        "horizon-traces-final": "staged Host mode2/Horizon30ms from actual compile receipts",
        "native-horizon": "normal generated mode2/Horizon300ms; no timing -D overrides",
    },
)
(TASK / f"{tag}-inputs.json").write_text(json.dumps(payload, indent=2), encoding="utf8")
print(f"Captured {len(sources)} source files and {len(payload['input_files'])} input files")
