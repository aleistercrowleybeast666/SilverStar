"""Fault-inject only disposable generated ownership metadata, restore exact bytes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
project = (ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v6/final/Flight_Controller").resolve()
path = project / ".fccg/ownership.json"
backup = project / ".fccg/ownership.pre-coverage.json"
assert path.resolve().is_relative_to(project) and backup.resolve().is_relative_to(project)
assert not backup.exists()
original = path.read_bytes()
rows = []
for mode in ("missing-file", "missing-active"):
    try:
        if mode == "missing-file":
            path.rename(backup)
        else:
            record = json.loads(original)
            record["active_components"].remove("silverstar.device.storage.sdmmc_fatfs_h7")
            path.write_text(json.dumps(record),encoding="utf8")
        command = [shutil.which("mingw32-make"),"-C",str(project),"power10-check"]
        log = EVIDENCE / ("coverage-post-"+mode+".log")
        with log.open("w",encoding="utf8") as output:
            result = subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        text = log.read_text(encoding="utf8")
        rows.append({"mode":mode,"command":command,"exit_code":result.returncode,
            "sources_scanned":len(re.findall(r"^POWER10_SOURCE\|",text,re.MULTILINE)),
            "owning_files_scanned":len(re.findall(r"^POWER10_SOURCE\|FATFS",text,re.MULTILINE))})
        assert result.returncode != 0
        assert "requires matching Make and active owner identities" in text
    finally:
        if backup.exists():
            backup.rename(path)
        else:
            path.write_bytes(original)
        assert path.read_bytes() == original
record = {"original_ownership_sha256":hashlib.sha256(original).hexdigest(),
          "metadata_restored_exactly":True,"rows":rows}
(EVIDENCE / "coverage-metadata-post.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps(record,indent=2),flush=True)
