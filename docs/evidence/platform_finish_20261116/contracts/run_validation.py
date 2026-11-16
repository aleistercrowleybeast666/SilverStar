"""Replay this finite contract batch against a separately generated project."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ARM = Path("D:/Arm GNU Toolchain/14.3 rel1/bin")
HOST = Path("D:/msys64/ucrt64/bin")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replica", choices=("a", "b"), default="a")
    parser.add_argument("--extra", action="store_true", help="Only the three remaining Release gates on an already built immutable project")
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join((str(ARM), str(HOST), str(Path(sys.executable).parent), env["PATH"]))
    records = []
    expected = []
    for configuration in ("Release", "Debug"):
        targets = ["all", "artifact-check", "stack-report"]
        if configuration == "Release" and args.replica == "a":
            targets += ["architecture-check", "power10-check", "static-analysis"]
        for target in targets:
            expected.append((configuration, target))
    if args.extra:
        expected = [("Release", target) for target in ("architecture-check", "power10-check", "static-analysis")]
    input_hashes = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in project.rglob("*") if path.is_file()
                    and path.relative_to(project).parts[0] not in (".fccg", "build", ".git")}
    (output / "generated-inputs.json").write_text(json.dumps(input_hashes, indent=2) + "\n", encoding="utf8")
    for configuration, target in expected:
        command = [str(HOST / "mingw32-make.exe"), "-C", str(project), "-j4",
                   "CONFIG=" + configuration, "GCC_PATH=" + str(ARM),
                   "PYTHON=" + sys.executable, target]
        log = output / (configuration + "-" + target + ".log")
        started = time.time()
        with log.open("wb") as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False)
        records.append({"argv": command, "cwd": str(ROOT), "started_unix": started,
                        "seconds": round(time.time() - started, 3), "exit": result.returncode,
                        "configuration": configuration, "gate": target,
                        "log": log.name, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        (output / "commands.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
        print(configuration, target, result.returncode, flush=True)
    after = {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in input_hashes}
    changed = [name for name, digest in input_hashes.items() if digest != after[name]]
    (output / "input-stability.json").write_text(json.dumps({"changed": changed}, indent=2) + "\n", encoding="utf8")
    # A must demonstrate the strict rejection before separate manual admission.
    failed = [row for row in records if row["exit"] != (2 if args.replica == "a" and row["gate"] == "stack-report" else 0)]
    return int(bool(failed or changed))


if __name__ == "__main__":
    raise SystemExit(main())
