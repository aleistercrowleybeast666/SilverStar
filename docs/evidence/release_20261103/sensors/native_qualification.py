"""Compile the emitted installation qualification unit and run physical-port faults."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
project, work, result = map(Path, sys.argv[1:4])
project = project.resolve()
work.mkdir(parents=True, exist_ok=False)
source = project / "Modules/InstallationCapture/Src/system_installation_capture.c"
fixture = ROOT / "apps/SCG/tests/fixtures/sensors/test_native_qualification.c"
graph = (project / "Generated/project_sources.mk").read_text(encoding="utf8")
block = graph.split("C_INCLUDES +=", 1)[1].split("\n\n", 1)[0]
inc = [name for name in block.replace(chr(92), " ").split() if (project / name).is_dir()]
assert "Platform/Inc" in inc and "Modules/InstallationCapture/Inc" in inc
exe = (work / "qualification.exe").resolve()
cmd = ["gcc", "-std=c11", "-O2", "-flto", "-fwhole-program", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
       "-Wall", "-Wextra", "-Werror", "-pedantic", "-fanalyzer", "-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1U",
       *["-I"+str(project/p) for p in inc], str(source), str(fixture), "-lm", "-o", str(exe)]
rows = []
for argv in (cmd, [str(exe)]):
    row = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    rows.append(dict(command=argv, exit_code=row.returncode, stdout=row.stdout, stderr=row.stderr))
    result.write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(), rows=rows), indent=2),encoding="utf8")
    if row.returncode: raise SystemExit(row.returncode)
