"""Run unmodified generated H743 gates against this exact fresh output."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
PROJECT = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v6/final/Flight_Controller"
make = shutil.which("mingw32-make")
arm = shutil.which("arm-none-eabi-gcc")
host = shutil.which("gcc")
if not all((make, arm, host)):
    raise RuntimeError("Actual ARM GCC/Host GCC/Make are required")
commands = []
for target in ("all", "architecture-check", "power10-check", "static-analysis", "artifact-check", "stack-report"):
    command = [make, "-C", str(PROJECT), "-j2", "CONFIG=Release", "GCC_PATH="+str(Path(arm).parent),
               "HOST_CC="+host, "PYTHON="+sys.executable, target]
    started = time.monotonic()
    with (EVIDENCE/(target+".log")).open("w",encoding="utf8") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    commands.append({"command":command,"exit_code":result.returncode,"seconds":time.monotonic()-started})
    (EVIDENCE/"commands.json").write_text(json.dumps(commands,indent=2)+"\n",encoding="utf8")
    print(target,result.returncode,flush=True)
inventory = [{"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,
    "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"owner":"algorithm_sdk",
    "purpose":"fresh H7 storage validation; not a user hardware candidate"}
    for p in sorted(PROJECT.rglob("*")) if p.is_file()]
(EVIDENCE/"inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf8")
raise SystemExit(int(any(row["exit_code"] for row in commands)))
