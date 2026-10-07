import hashlib
import json
from pathlib import Path
import re

repo = next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
docs = ['README.md','docs/README.md','docs/USER_WORKFLOW.md',
 'docs/algorithms/NAVIGATION_IMPLEMENTATION.md','docs/FLP/SF6_Replay.md',
 'docs/SilverStar_Recommended_Configurations.md','docs/NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md']
missing=[]
links=[]
for name in docs:
    path=repo/name
    if not path.exists():
        missing.append(name)
        continue
    for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf8')):
        if dest.startswith(('https:','http:','app:','#')):
            continue
        dest=dest.split('#')[0]
        target=(path.parent/dest).resolve()
        links.append({'source':name,'target':str(target.relative_to(repo)), 'exists':target.exists()})
        if not target.exists(): missing.append(name+' -> '+dest)
result={'documents':docs,'links':links,'missing':missing}
output = repo/'.work/nightly_closeout_doc_links.json'
output.write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({'link_count':len(links),'missing':missing}))
raise SystemExit(bool(missing))
