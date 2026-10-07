import hashlib
import json
from pathlib import Path
import subprocess

runner=Path(__file__).resolve().parent
repo=next(p for p in runner.parents if (p/'.git').exists())
evidence=repo/'docs/evidence/nightly_software_20261008'
manifest=json.loads((evidence/'manifest.json').read_text(encoding='utf8'))
source=json.loads((evidence/'source_hashes_v4.json').read_text(encoding='utf8'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
source_changed=[p for p,h in source.items() if digest(repo/p)!=h]
evidence_changed=[p for p,v in manifest['files'].items() if digest(evidence/p)!=v['sha256']]
inventory_changed=[p for p,h in manifest['inventory_files'].items() if digest(repo/p)!=h]
result={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
 'branch':subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip(),
 'application_source_mismatches':source_changed,'evidence_mismatches':evidence_changed,
 'inventory_mismatches':inventory_changed}
print(json.dumps(result,indent=2))
raise SystemExit(bool(source_changed or evidence_changed or inventory_changed))
