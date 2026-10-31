"""Check retained CubeMX identities, one compiled owner and emitted C faults."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / "apps/SCG"
EVIDENCE = Path(__file__).resolve().parent
PROJECT = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v4/final/Flight_Controller"
CUBE = ROOT / ".work/h7_20261025/verified_release/CubeMX_StaticInput"
sys.path.insert(0, str(SCG / "src"))
receipt = json.loads((PROJECT / ".fccg/ownership.json").read_text())["hardware"]["storage_replacement"]
manifest = json.loads((SCG / "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7/plugin.json").read_text(encoding="utf8"))
expected = manifest["metadata"]["h7_storage_replacement"]["required_input_sha256"]
rows = []
for relative, digest in expected.items():
    original = CUBE / relative.removeprefix("HardwareGenerated/STM32CubeMX/")
    row = {"path": relative, "expected": digest,
           "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
           "retained_sha256": hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest()}
    assert row["source_sha256"] == row["retained_sha256"] == digest
    rows.append(row)
make = (PROJECT / "Generated/project_sources.mk").read_text()
eide = (PROJECT / ".eide/eide.yml").read_text()
owners = []
for original, replacement in receipt["replacements"].items():
    assert make.count("  "+original) == 0 and make.count("  "+replacement) == 1
    assert eide.count("- path: "+replacement) == 1 and eide.count("- path: "+original) == 0
    assert eide.count("      - "+original) == 2  # Debug and Release exclusions.
    source = SCG / "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7/payload" / replacement
    assert source.read_bytes() == (PROJECT / replacement).read_bytes()
    owners.append({"path": replacement,"sha256":hashlib.sha256(source.read_bytes()).hexdigest()})
for name in ("run_storage_integrity.py", "test_storage_integrity.c", "test_logger_storage.c"):
    relative = "Tests/Host/storage_integrity/" + name
    source = SCG / "plugins/builtin/silverstar_core_0_1_0/payload" / relative
    assert source.read_bytes() == (PROJECT / relative).read_bytes()
(EVIDENCE / "input-owner-audit.json").write_text(json.dumps({
    "verified_inputs":rows,"active_owner":owners,"make_and_eide_match":True,
    "emitted_host_matches_owner":True,"receipt":receipt},indent=2)+"\n")
spec = importlib.util.spec_from_file_location("h7_tests", SCG / "tests/test_h7_storage_replacement.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
destination = PROJECT.parent / "late-boundary"
destination.mkdir(exist_ok=False)
source = PROJECT / "FATFS/Target/sd_diskio.c"
binary = fixture.DiskioFixture_Compile(destination, source)
results = []
for mode in range(5):
    command = [str(binary), str(mode)]
    result = subprocess.run(command, capture_output=True, text=True)
    results.append({"mode":mode,"command":command,"exit_code":result.returncode,
                    "stdout":result.stdout,"stderr":result.stderr})
record = {"source":str(source),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
          "binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),"results":results}
(EVIDENCE / "late-boundary-final.json").write_text(json.dumps(record,indent=2)+"\n")
versions = {}
for executable in (sys.executable, shutil.which("gcc"), shutil.which("arm-none-eabi-gcc"), shutil.which("mingw32-make")):
    result = subprocess.run([executable,"--version"],capture_output=True,text=True)
    versions[executable] = {"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr}
(EVIDENCE / "tool-versions.json").write_text(json.dumps(versions,indent=2)+"\n")
print(json.dumps(record,indent=2))
raise SystemExit(int(any(row["exit_code"] for row in results)))
