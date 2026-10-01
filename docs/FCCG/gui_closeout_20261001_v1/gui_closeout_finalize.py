import hashlib
import json
import pathlib
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
evidence = root/'docs/FCCG/gui_closeout_20261001_v1'
(evidence/'candidate_source.diff').write_bytes(subprocess.check_output(['git','diff','--binary','HEAD'], cwd=root))
paths = subprocess.check_output(['git','diff','--name-only','HEAD'], cwd=root).decode().splitlines()
paths += subprocess.check_output(['git','ls-files','--others','--exclude-standard','SCG.py','apps/FCCG','apps/FLP','apps/GSHC'], cwd=root).decode().splitlines()
hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sorted(set(paths)) if (root/name).is_file()}
(evidence/'candidate_source_sha256.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
generated = root/'.work/SCG_Closeout_2175d95_v4'
files = {str(path.relative_to(generated)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in generated.rglob('*') if path.is_file()}
(evidence/'generated_v4_sha256.json').write_text(json.dumps(files, indent=2)+'\n', encoding='utf-8')
for name in ('gui_closeout_candidate_evidence.py','gui_closeout_finalize.py'):
    shutil.copy2(root/'.work'/name, evidence/name)
print('Final candidate:', len(hashes), 'source files;', len(files), 'generated files; historical snapshots preserved.')
