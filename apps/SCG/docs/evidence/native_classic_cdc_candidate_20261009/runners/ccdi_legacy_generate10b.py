from pathlib import Path
import hashlib,json,subprocess
ROOT=Path('D:/python_software/SilverStar')
REPO=ROOT/'.work/ccdi'
OUT=ROOT/'.work/ccdi-evidence10b'
paths=['apps/SCG/src/silverstar_fccg/app/service.py','apps/SCG/src/silverstar_fccg/generator/multi_target.py',
       'apps/SCG/src/silverstar_fccg/hardware/native_classic_cdc.py','apps/SCG/tests/test_native_classic_cdc.py',
       'apps/SCG/tools/validation/native_classic_cdc_compile.py']
hashes={p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in paths}
for p in paths:
    target=OUT/'source_snapshot'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((REPO/p).read_bytes())
receipt={'head':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
         'dirty_diff':subprocess.check_output(['git','-C',str(REPO),'diff','--binary'],text=True),
         'source_sha256':hashes}
(OUT/'source_snapshot.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
source=(ROOT/'.work/ccdi_legacy_generate.py').read_text(encoding='utf-8').replace('sscdc-legacy10a','sscdc-legacy10b')
# The wrapper's original script replacement must be applied to its embedded text.
source=source.replace('"sscdc-legacy10b")', '"sscdc-legacy10b")')
exec(compile(source,'ccdi_legacy_generate10b','exec'))
assert all(hashlib.sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
