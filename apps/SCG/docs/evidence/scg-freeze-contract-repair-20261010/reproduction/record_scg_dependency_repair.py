from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, hashlib, xml.etree.ElementTree as ET, ast

task=Path(__file__).parent;repo=task/'r'
def git(*args): return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
paths=['apps/GSHC/protocol/air.py','apps/GSHC/protocol/common.py','apps/GSHC/protocol/gsp_min.py',
 'apps/GSHC/protocol/receive_pipeline.py',
 'docs/evidence/logger_health_retest_20261008/generated_config.ssproject',
 'docs/evidence/scg_decoder_binding_20261008/evidence.zip']
files={}
for name in paths:
 blob=git('rev-parse','HEAD:'+name)
 assert git('hash-object',name)==blob, name
 files[name]={'git_blob':blob,'sha256':hashlib.sha256((repo/name).read_bytes()).hexdigest(),
              'bytes':(repo/name).stat().st_size}
failures=[]
for case in ET.parse(task/'srf01.xml').getroot().findall('.//testcase'):
 failure=case.find('failure')
 if failure is not None:
  failures.append({'name':case.get('classname','')+'::'+case.get('name',''),
                   'message':failure.get('message',''),'detail':failure.text})
assert len(failures)==5
prior=subprocess.check_output(['git','-C',str(repo),'show',
 '24462e4aaede867e70dbecef4ab67e2a1c8adf8b:apps/SCG/src/silverstar_fccg/hardware/platform.py'],text=True)
current=(repo/'apps/SCG/src/silverstar_fccg/core/platform_tokens.py').read_text()
old=next(node for node in ast.parse(prior).body if isinstance(node,ast.FunctionDef) and node.name=='_Token_Get')
new=next(node for node in ast.parse(current).body if isinstance(node,ast.FunctionDef) and node.name=='PlatformToken_Get')
same=tuple(ast.dump(node) for node in old.body)==tuple(ast.dump(node) for node in new.body)
assert same
review=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-09\task-2\scg-review-244')
data={'recorded_utc':datetime.now(timezone.utc).isoformat(),'source_commit':git('rev-parse','HEAD'),
 'sparse_dependency_repair':{'classification':'Five setup failures at 24462e4: absent unchanged parser and two committed historical fixtures. Exact committed files checked out; no test-body redirect or assertion relaxation, no GSHC code changes.',
 'failed_run':'srf01','failures':failures,'files':files,'sparse_patterns':git('sparse-checkout','list')},
 'ordinary_review_p2':{'reviewed_commit':'24462e4aaede867e70dbecef4ab67e2a1c8adf8b',
 'finding':'Catalog raw exact_part domains disagree with actual matcher normalization; three equivalent spellings falsely appeared disjoint.',
 'fixed_commit':'819eec98347e96aa6548012be159e6a6c58bd435',
 'matcher_normalizer_ast_body_unchanged':same,
 'shared_function':'core/platform_tokens.py:PlatformToken_Get',
 'regression':'Three same-target spelling collisions reject in actual Scan before publication, proven against actual runtime matcher; distinct target and empty canonical token covered.',
 'review_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in review.iterdir() if p.is_file() and p.name in {'review.md','audit.json','evidence-summary.json'}}},
 'precommit_import_error':'srnorm01 exit 4, circular hardware package import introduced by initial shared-module location; corrected by moving to core, no test assertions/guards bypassed. srnorm02 fourteen passes. Logs remain.'}
(task/'sr-dependency-and-p2-repair.json').write_text(json.dumps(data,indent=2))
print(json.dumps({'source_commit':data['source_commit'],'files':len(files),'five_setup_failures':len(failures),'normalizer_body_unchanged':same},indent=2))
