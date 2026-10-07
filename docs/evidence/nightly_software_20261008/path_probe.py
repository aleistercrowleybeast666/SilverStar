import json
import os
from pathlib import Path

repo=next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
base=repo/'.work/path_probe_nc08'
base.mkdir(exist_ok=False)
directory=base/('d'*155)
directory.mkdir()
source=directory/'records.tmp'
destination=directory/('a'*64+'.records.json.gz')
source.write_bytes(b'path-contract')
result={'source_length':len(str(source)),'destination_length':len(str(destination))}
try:
    os.replace(source,destination)
    result['ordinary_replace']='PASS'
except OSError as exc:
    result['ordinary_replace']={'winerror':exc.winerror,'error':str(exc)}
    try:
        os.replace('\\\\?\\'+str(source),'\\\\?\\'+str(destination))
        result['extended_replace']='PASS'
    except OSError as other:
        result['extended_replace']={'winerror':other.winerror,'error':str(other)}
for name,action in [('stat',lambda:destination.stat().st_size),
                    ('read',lambda:destination.read_bytes().decode()),
                    ('glob',lambda:[p.name for p in directory.iterdir()]),
                    ('unlink',lambda:destination.unlink())]:
    try: result[name]=action()
    except OSError as exc: result[name]={'winerror':exc.winerror,'error':str(exc)}
print(json.dumps(result,indent=2))
