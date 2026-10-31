"""Compile actual emitted diskio with the same normal/fault expectations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))
spec = importlib.util.spec_from_file_location("h7_tests", SCG / "tests/test_h7_storage_replacement.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
project = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v4/post-fix/Flight_Controller"
source = project / "FATFS/Target/sd_diskio.c"
destination = project.parent / "late-boundary"
destination.mkdir(exist_ok=False)
binary = fixture.DiskioFixture_Compile(destination, source)
results = []
for mode in range(5):
    command = [str(binary), str(mode)]
    result = subprocess.run(command, capture_output=True, text=True)
    results.append({"mode": mode, "command": command, "exit_code": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr})
evidence = {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "fixture_sha256": hashlib.sha256((SCG / "tests/fixtures/h7_diskio/test_diskio_faults.c").read_bytes()).hexdigest(),
            "results": results}
Path(__file__).with_name("late-boundary-results.json").write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf8")
print(json.dumps(evidence, indent=2))
raise SystemExit(int(any(row["exit_code"] for row in results)))
