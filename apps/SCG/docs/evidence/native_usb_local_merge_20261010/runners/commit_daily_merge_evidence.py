from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib
repo=Path(r'D:\python_software\SilverStar');task=Path(__file__).parent;root='apps/SCG/docs/evidence/native_usb_local_merge_20261010';report='apps/SCG/docs/NATIVE_USB_LOCAL_MERGE_20261010.md'
code='e1357b417ee98df5990a1fff18c55d6b35183896';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],text=True).strip()
assert git('rev-parse','HEAD')==code and git('branch','--show-current')=='fix/nightly-user-ready-20261003'
checked=json.loads((task/'daily-merge-final-archive.json').read_text());assert checked['manifest_sha256']==sha(repo/root/'verification.json') and checked['report_sha256']==sha(repo/report)
staged=git('diff','--cached','--name-only').splitlines();assert len(staged)==checked['verified_index_and_working_files']+1 and all(p.startswith(root+'/') or p==report for p in staged)
assert not git('diff','--name-only')
subprocess.run(['git','-C',str(repo),'commit','-m','Record local USB candidate merge and daily software verification'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
head=git('rev-parse','HEAD');expected=['?? work_build_candidates_20261006.csv','?? work_inventory_20261006.txt','?? work_subtree_classification_20261006.csv'];assert git('status','--porcelain').splitlines()==expected
preflight=json.loads((task/'usb-daily-merge-preflight.json').read_text())
for p,digest in preflight['preserved_untracked_sha256'].items():assert sha(repo/p)==digest
assert git('rev-parse',preflight['backup_ref'])==preflight['before_head']
assert all(p.startswith('apps/SCG/') for p in git('diff','--name-only',preflight['before_head'],'HEAD').splitlines())
assert git('diff','--name-only',code,'HEAD') and all(p.startswith(root+'/') or p==report for p in git('diff','--name-only',code,'HEAD').splitlines())
d={'daily_head':head,'daily_branch':git('branch','--show-current'),'merge_commit':'2016a1279fa529c96d5b108d7d67326e2fda3653',
 'tested_daily_delivery_commit':code,'source_code_commit':'f61cbd851b8ac32b865deb1a3997058685dfebbd','source_evidence_commit':'5b99438ba4005ea02935e9734307e749e2e758e7',
 'backup_ref':preflight['backup_ref'],'before_head':preflight['before_head'],'status':expected,'no_tracked_modifications':True,
 'preserved_user_files_sha256':preflight['preserved_untracked_sha256'],'report_sha256':sha(repo/report),'manifest_sha256':sha(repo/root/'verification.json'),
 'archive_files':checked['verified_index_and_working_files'],'archived_bytes':checked['archived_bytes'],
 'normal_tests':{'gui':12,'regression':99,'async':16,'direct_formal_guards':5,'emitted_gates':8},'default_python_startup':'passed offscreen with temporary writable user state',
 'extra_generic_to_pinned_f103_equality_test':'failed authority path/hash equality; retained, factual fields otherwise equal',
 'formal_release':False,'independent_usb_safety_review':'NO_PASSED_OUTCOME','hardware_actions':False,'push_or_publish':False,
 'own_running_builds_or_tests':[],'os_wide_process_inventory':'Not certified; only owned sessions tracked',
 'recorded_utc':datetime.now(timezone.utc).isoformat()}
(task/'daily-merge-final-delivery.json').write_text(json.dumps(d,indent=2),encoding='utf8');print(json.dumps(d,indent=2))
