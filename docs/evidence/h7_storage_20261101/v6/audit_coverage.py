"""Assert actual positive coverage and unchanged F407 source classification."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
WORK = ROOT / ".work/0.1.3-treediagram-20261101"
power = (EVIDENCE / "power10-check.log").read_text(encoding="utf8")
analyzer = (EVIDENCE / "static-analysis.log").read_text(encoding="utf8")
rows = []
for name in ("sd_diskio.c", "bsp_driver_sd.c"):
    source = "FATFS/Target/" + name
    token = "POWER10_SOURCE|" + source.replace("/", "\\") + "|"
    scanned = [line for line in power.splitlines() if line.startswith(token)]
    compiled = [line for line in analyzer.splitlines() if " -c " in line and
                " "+source+" -o " in line and " -fanalyzer " in line and " -Werror " in line]
    assert len(scanned) == len(compiled) == 1
    rows.append({"source":source,"power10":scanned[0],"strict_analyzer_command":compiled[0]})
baseline = (EVIDENCE.parent / "v4/f407-power10-coverage-baseline.log").read_text(encoding="utf8")
current = (EVIDENCE / "f407-power10.log").read_text(encoding="utf8")
source_lines = lambda text: [line for line in text.splitlines() if line.startswith("POWER10_SOURCE|")]
assert source_lines(baseline) == source_lines(current)
old_make = (WORK / "h7-storage-v4/f407-final/Flight_Controller/Makefile").read_bytes()
new_make = (WORK / "h7-storage-v6/f407-final/Flight_Controller/Makefile").read_bytes()
assert old_make == new_make
ownership = json.loads((WORK / "h7-storage-v6/final/Flight_Controller/.fccg/ownership.json").read_text(encoding="utf8"))
record = {"h7_owner_coverage":rows,"f407_make_unchanged":True,
          "f407_make_sha256":hashlib.sha256(new_make).hexdigest(),
          "f407_power10_source_lines_identical":True,"f407_first_party_files":len(source_lines(current)),
          "h7_first_party_files":len(source_lines(power)),"upstream_components":ownership["upstream_components"],
          "scope":"Exact H7 owning units added; no vendor/middleware reclassification or threshold exceptions."}
(EVIDENCE / "coverage-audit.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf8")
print(json.dumps({key:value for key,value in record.items() if key not in ("h7_owner_coverage","upstream_components")},indent=2))
