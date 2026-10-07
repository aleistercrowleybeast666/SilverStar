import ast
import json
from pathlib import Path
import re
out=Path(__file__).resolve().parent
data=[]
for line in (out/'flp_combined_v2.log').read_text(encoding='utf8',errors='replace').splitlines():
    if not line.startswith('E ') or 'FileNotFoundError:' not in line: continue
    literals=re.findall(r"'(D:\\\\[^']+)'",line)
    paths=[ast.literal_eval("'"+literal+"'") for literal in literals]
    data.append({'paths':paths,'lengths':[len(p) for p in paths]})
(out/'path_limits.json').write_text(json.dumps(data,indent=2),encoding='utf8')
print(json.dumps([row['lengths'] for row in data]))
