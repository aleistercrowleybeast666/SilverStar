"""Compile the three fresh analysis candidates; never mutate their sources."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent / "build-v1"
WORK = ROOT / ".work/0.1.3-software-completion-20261101/stack/v2/analysis"
GCC = Path("D:/Arm GNU Toolchain/14.3 rel1/bin")
HOST = Path("D:/msys64/ucrt64/bin")
environment = os.environ.copy()
environment["PATH"] = os.pathsep.join((str(GCC), str(HOST), str(Path(sys.executable).parent), environment["PATH"]))


def Build_Run(name, configuration):
    project = WORK / name / "Flight_Controller"
    commands = []
    for target in ("all", "artifact-check"):
        command = [str(HOST / "mingw32-make.exe"), "-C", str(project), "-j4",
                   "CONFIG=" + configuration, "GCC_PATH=" + str(GCC), "PYTHON=" + sys.executable, target]
        log = OUT / (name + "-" + configuration + "-" + target + ".log")
        start = time.monotonic()
        with log.open("w", encoding="utf8") as stream:
            result = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        commands.append({"name": name, "configuration": configuration, "command": command,
            "exit_code": result.returncode, "seconds": round(time.monotonic() - start, 3),
            "log": log.name, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        print(name, configuration, target, result.returncode, flush=True)
        if target == "all" and result.returncode:
            break
    return commands


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=False)
    records = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(Build_Run, name, configuration)
                   for name in ("f407", "installation", "h743") for configuration in ("Release", "Debug")]
        for future in as_completed(futures):
            records.extend(future.result())
            (OUT / "commands.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
    raise SystemExit(int(any(row["exit_code"] for row in records)))
