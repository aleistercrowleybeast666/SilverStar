from pathlib import Path
import json, hashlib, shutil, datetime
root=Path(__file__).resolve().parent;repo=root.parents[1]
formal=repo/'docs/evidence/static_log_file_20261008'
manifest=json.loads((formal/'manifest.json').read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,row in manifest['files'].items():
    assert sha(formal/name)==row['sha256'],name
for name in ['final_verify_v2.log','seal_evidence.py']:
    assert not (formal/'execution'/name).exists()
    shutil.copyfile(root/name,formal/'execution'/name)
manifest['commands'].insert(-1,{'command':'apps/FLP/.venv/Scripts/python.exe .work/flp08tf/final_verify.py',
    'exit':1,'scope':'Verifier read UTF-8 source filename inventory with Windows default encoding; no product change. Failure log and script retained.'})
manifest['final_verifier_encoding']='Explicit UTF-8 in final_verify_v2.py; independent verification passed'
manifest['sealed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest['files']={str(p.relative_to(formal)):{'bytes':p.stat().st_size,'sha256':sha(p)}
    for p in formal.rglob('*') if p.is_file() and p!=formal/'manifest.json'}
(formal/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'files':len(manifest['files'])+1,'bytes':sum(r['bytes'] for r in manifest['files'].values()),
                  'manifest_sha256':sha(formal/'manifest.json')}))
