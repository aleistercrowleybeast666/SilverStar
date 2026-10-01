from pathlib import Path
import subprocess,hashlib,json,re
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
base='apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/'
report=[]
for name in ('navigation_sf6.c','navigation_sf6_backend.c'):
    spec='4703835:'+base+name
    blob=subprocess.check_output(['git','show',spec],cwd=root)
    item=dict(file=base+name,git_blob_id=subprocess.check_output(['git','rev-parse',spec],cwd=root,text=True).strip(),
              git_blob_content_sha256=hashlib.sha256(blob).hexdigest(),
              git_content_all_crlf_sha256=hashlib.sha256(blob.replace(b'\n',b'\r\n')).hexdigest())
    raw_path=out/'CrossGroup_PreFix'/name
    if raw_path.exists():
        raw=raw_path.read_bytes();crlf=raw.count(b'\r\n')
        item.update(archived_worktree_raw_sha256=hashlib.sha256(raw).hexdigest(),
                    crlf_lines=crlf,lf_only_lines=raw.count(b'\n')-crlf,cr_only=raw.count(b'\r')-crlf,
                    normalized_to_lf_equals_git_content=raw.replace(b'\r\n',b'\n')==blob)
    report.append(item)
(out/'hash_object_reconciliation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
