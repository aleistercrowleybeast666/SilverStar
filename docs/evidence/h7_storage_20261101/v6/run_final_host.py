"""Run the emitted complete storage runner, not the broader make host-tests."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
name = sys.argv[1]
if name not in ("h743", "f407"):
    raise ValueError("exact candidate required")
project = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v6" / (
    "final" if name == "h743" else "f407-final") / "Flight_Controller"
command = [sys.executable, str(project / "Tests/Host/storage_integrity/run_storage_integrity.py"),
           "--project", str(project), "--compiler", shutil.which("gcc")]
started = time.monotonic()
with (EVIDENCE / (name+"-storage-host.log")).open("w",encoding="utf8") as output:
    result = subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
(EVIDENCE / (name+"-storage-host-command.json")).write_text(json.dumps({
    "command": command, "exit_code": result.returncode, "seconds": time.monotonic()-started,
    "scope": "complete emitted storage_integrity runner; not complete make host-tests"},indent=2)+"\n")
print(name, result.returncode, flush=True)
raise SystemExit(result.returncode)
