"""Run the actual emitted gates without combining earlier candidate passes."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    version, model, folder = sys.argv[1:4]
    project = ROOT / ".work/release-20261103/sensors" / version / model / "Flight_Controller"
    output = HERE / folder
    output.mkdir(parents=True, exist_ok=True)
    record = output / (model + "-commands.json")
    assert not record.exists()
    rows = []
    for configuration, gates in [("Release", ("all", "architecture-check", "power10-check",
            "artifact-check", "stack-report", "static-analysis")),
            ("Debug", ("all", "artifact-check", "stack-report"))]:
        for gate in gates:
            stem = model + "-" + configuration + "-" + gate
            command = ["mingw32-make", "-C", str(project), "-j5",
                       "GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin", "CONFIG=" + configuration, gate]
            start = time.time()
            with (output / (stem + ".log")).open("xb") as stream:
                code = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT).returncode
            rows.append(dict(command=command, exit_code=code, duration_s=round(time.time()-start, 2)))
            record.write_text(json.dumps(rows, indent=2)+"\n", encoding="utf8")
            print(stem, code, flush=True)


if __name__ == "__main__":
    main()
