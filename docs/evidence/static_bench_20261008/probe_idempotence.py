from pathlib import Path
import sys,json,hashlib,difflib
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
out=Path(__file__).resolve().parent
target=repo/'.work/b08_idempotence'
assert not target.exists()
s=FccgService(repo/'apps/SCG')
m=s.ReferenceProject_Create('BenchIdempotence')
first=s.Project_Save(m,target)
before={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
second=s.Project_Save(m,target)
changes=[]
for p in target.rglob('*'):
    if p.is_file():
        n=p.relative_to(target).as_posix();new=p.read_bytes();old=before.get(n)
        if old!=new:
            item={'file':n,'old_sha256':hashlib.sha256(old).hexdigest() if old else None,'new_sha256':hashlib.sha256(new).hexdigest()}
            if p.suffix not in ('.ssdecoder',):
                item['diff']=''.join(difflib.unified_diff((old or b'').decode('utf-8',errors='replace').splitlines(True),new.decode('utf-8',errors='replace').splitlines(True)))
            changes.append(item)
result={'first':str(first),'second':str(second),'changes':changes}
(out/'idempotence_probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2),flush=True)
