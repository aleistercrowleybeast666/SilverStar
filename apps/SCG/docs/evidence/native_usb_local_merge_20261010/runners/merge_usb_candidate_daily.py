from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib
repo=Path(r'D:\python_software\SilverStar');task=Path(__file__).parent
candidate='5b99438ba4005ea02935e9734307e749e2e758e7';code='f61cbd851b8ac32b865deb1a3997058685dfebbd'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
before=git('rev-parse','HEAD');branch=git('branch','--show-current');status=git('status','--porcelain').splitlines()
assert before=='56448bd35736221d7885a26704f2f953b0fe5055' and branch=='fix/nightly-user-ready-20261003'
assert status==['?? work_build_candidates_20261006.csv','?? work_inventory_20261006.txt','?? work_subtree_classification_20261006.csv'],status
assert git('merge-base','HEAD',candidate)==before
names=git('diff','--name-only',before,candidate).splitlines();assert names and all(p.startswith('apps/SCG/') for p in names)
assert not any(p.upper().startswith('APPS/SCG/FINAL/') or '/.VENV/' in p.upper() for p in names)
original={p[3:]:hashlib.sha256((repo/p[3:]).read_bytes()).hexdigest() for p in status}
backup='backup/pre-usb-candidate-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
record={'before_head':before,'branch':branch,'before_status':status,'preserved_untracked_sha256':original,'backup_ref':backup,
 'candidate_evidence_commit':candidate,'tested_code_commit':code,'diff_paths':names,'scope':'SCG only; local merge of independently accepted exact-target experimental candidate; no hardware, FINAL, push or publish',
 'started_utc':datetime.now(timezone.utc).isoformat()}
(task/'usb-daily-merge-preflight.json').write_text(json.dumps(record,indent=2),encoding='utf8')
subprocess.run(['git','-C',str(repo),'branch',backup,before],check=True)
result=subprocess.run(['git','-C',str(repo),'merge','--no-ff','-m','Merge validated exact-target USB Ground experimental candidate',candidate],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(task/'usb-daily-merge.log').write_text(result.stdout,encoding='utf8')
record.update(merge_exit=result.returncode,after_head=git('rev-parse','HEAD'),after_status=git('status','--porcelain').splitlines(),finished_utc=datetime.now(timezone.utc).isoformat())
assert original=={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in original},'User file bytes changed'
(task/'usb-daily-merge-receipt.json').write_text(json.dumps(record,indent=2),encoding='utf8')
assert result.returncode==0,'Substantive merge conflict; preserve files and report instead of resolving'
assert record['after_status']==status,record['after_status']
assert git('diff','--name-only',candidate,'HEAD')=='','Merge result differs from validated candidate'
print(json.dumps({k:record[k] for k in ['before_head','after_head','branch','backup_ref','merge_exit','after_status']},indent=2))
