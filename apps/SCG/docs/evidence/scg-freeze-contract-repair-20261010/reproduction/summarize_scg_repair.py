from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, subprocess, xml.etree.ElementTree as ET

task = Path(__file__).parent
repo = task / 'r'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def git(path,*args): return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def suite(label):
    cases=ET.parse(task/(label+'.xml')).getroot().findall('.//testcase')
    result={'label':label,'tests':len(cases),'passed':0,'failed':[],'skipped':[]}
    for case in cases:
        name=case.get('classname','')+'::'+case.get('name','')
        failure=case.find('failure'); error=case.find('error'); skipped=case.find('skipped')
        if failure is not None or error is not None:
            result['failed'].append({'name':name,'detail':ET.tostring(case,encoding='unicode')})
        elif skipped is not None:
            result['skipped'].append({'name':name,'reason':skipped.get('message',''),'detail':skipped.text or ''})
        else: result['passed']+=1
    command_path=task/(label+'-command.json')
    result['command']=json.loads(command_path.read_text()) if command_path.exists() else None
    if label=='ds-async01':
        result['command']=next(r for r in json.loads((task/'ds-resume-sequence.json').read_text()) if r['label']==label)
        result['raw_original_log_unavailable']=True
        result['scope']='Original XML contains preserved 12 pass/4 alias failures. Original command recovered from initial sequence. Current label log is import-sideeffect abort, explicitly archived separately.'
    result['evidence_sha256']={p.name:digest(p) for p in task.glob(label+'*') if p.is_file()}
    return result

final_info=json.loads((task/'sr-final-code.json').read_text(encoding='utf-8-sig'))
groups=[suite(label) for label in ['srb02','srgn03','sru02','ds-flight01','srgui01','ds-async03']]
historical=[suite(label) for label in ['srpre01','srpre02','srnorm02','srb01','srgn01','srgn02','sru01','srf01','srentry01','sra01','ds-async02']]
extra=[suite('srentry02'),suite('ds-entry01')]
gates=[]
for label in ['srng01','srpg02']:
    gates.extend({'label':label,**row} for row in json.loads((task/(label+'-gates.json')).read_text()))
for path in sorted(task.glob('srlegacy-*-command.json')):
    gates.append({'label':path.name,**json.loads(path.read_text())})
for label in ['ds-Flight-static-analysis','ds-Flight-artifact-check']:
    gates.append({'label':label,**json.loads((task/(label+'-command.json')).read_text())})

daily=Path(r'D:\python_software\SilverStar')
private=Path(r'D:\python_software\SilverStar\.work\ccdi')
data={
 'recorded_utc':datetime.now(timezone.utc).isoformat(),
 'base_commit':'2b3d4ae8889f1fb0924ee18631c6a346e5822b98',
 'main_repair_commit':'a0afca6a11a9cf7066baf62afecf95fd549c9736',
 'prior_ui_commit':final_info['prior_ui_commit'],
 'final_code_commit':final_info['final_code_commit'],
 'worktree':str(repo),'branch':git(repo,'branch','--show-current'),
 'current_head':git(repo,'rev-parse','HEAD'),'current_status':git(repo,'status','--porcelain'),
 'original_baseline':{'summary':'560 passed, 6 failed, 12 skipped; preserved, not rerun or erased',
  'evidence_sha256':{name:digest(task/name) for name in ['SCG_FREEZE_VERIFICATION_20261010.json','SCG_SIX_FAILURE_CLASSIFICATION_20261010.md','fz-artifact-evidence.json']}},
 'complete_module_groups':groups,'historical_repair_runs_not_counted_twice':historical,
 'precommit_import_error':json.loads((task/'srnorm01-command.json').read_text()),
 'dependency_and_p2_repair':json.loads((task/'sr-dependency-and-p2-repair.json').read_text()),
 'additional_direct_entry':extra,
 'totals':{'passed':sum(g['passed'] for g in groups),'failed':sum(len(g['failed']) for g in groups),'skipped':sum(len(g['skipped']) for g in groups),'tests':sum(g['tests'] for g in groups)},
 'gates':gates,'artifact_evidence':json.loads((task/'sr-artifact-evidence.json').read_text()),
 'startup':json.loads((task/'sr-startup.json').read_text()),
 'launcher':json.loads((task/'sr-launcher.json').read_text()),
 'tool_versions':json.loads((task/'fz-tool-versions.json').read_text()),
 'sequence':json.loads((task/'sr-sequence.json').read_text()),
 'async_final_response_metrics':[{'file':str(p),'sha256':digest(p),'data':json.loads(p.read_text())} for p in sorted(Path('D:/Codex_Work/task-temp/scg-final-819eec9/ds-async03').rglob('refresh-response.json'))],
 'D_migration_locator':json.loads((task/'ds-locator-migration.json').read_text()),
 'D_migration_quality':json.loads((task/'ds-migration-quality.json').read_text()),
 'evidence_correction':json.loads((task/'ds-evidence-correction.json').read_text()),
 'D_original_failed_sequence':json.loads((task/'ds-resume-sequence.json').read_text()),
 'D_alias_failure_original_xml':suite('ds-async01'),
 'migration_process_cancellation':json.loads(Path('D:/Codex_Work/migration-ledgers/scg-owned-processes-cancelled.json').read_text(encoding='utf-8-sig')),
 'ordinary_catalog_review_819':json.loads(Path('D:/Codex_Work/2026-10-09/task-2/scg-review-819-catalog/command.json').read_text()),
 'final_groups_sequence':json.loads((task/'sr-final-groups-sequence.json').read_text()),
 'historical_private_gates':json.loads((task/'srpg01-gates.json').read_text()),
 'daily':{'head':git(daily,'rev-parse','HEAD'),'status':git(daily,'status','--porcelain'),
   'user_untracked_sha256':{name:digest(daily/name) for name in ['work_build_candidates_20261006.csv','work_inventory_20261006.txt','work_subtree_classification_20261006.csv']}},
 'ccdi':{'head':git(private,'rev-parse','HEAD'),'status':git(private,'status','--porcelain')},
 'limits':[
  'C disk emergency interrupted srf02 and Flight analyzer without completion. Independent migration task terminated old owned processes; original ledgers retained. D serial continuation finishes only named remaining checks.',
  'ds-async01 retained 12 passes/4 alias refusal failures in original XML. ds-async02 retained 14 passes/2 correct stale quality failures after pointer relocation. Actual product APIs regenerated quality results, preserving old records and immutable model/receipt/ELF bytes.',
  'Evidence helper import sideeffect overwrote two early D raw logs/command files. Original failed async XML and original sequence metadata/hash survive; raw original log bytes unavailable. This limitation is explicitly archived, not silently relabeled.',
  'Every final complete group and native receipt runs at 819eec9 after ordinary review P2. Earlier a0afca6/24462e4 results and five sparse-checkout fixture failures remain historical, not relabeled as final pass.',
  'No test deselection in full groups; this is explicit affected module coverage, not every SCG test file.',
  'No original guard/assertion/identity hash/stack limit relaxed. Unified positive fixtures use actual importer; legacy rejection and source reimport have separate regressions.',
  'PoT F Prime-inspired text adaptation only, critical-contract acceptance NOT PROVEN; whole-program stack/WCET and hardware remain outside evidence.',
  'Formal USB BLOCKED, b66 independent safety review NO_PASSED_OUTCOME. No retry, bypass or malformed USB/owner-expression research.',
  'Original six failures/twelve skips and new srpre01 fixture setup failure remain archived. Receipt-discovery helper first selected unified receipts too; it was corrected to exclude actual unified index outputs without changing product code or gates.',
  'Known cache_dir warning occurs only because wrappers disable cacheprovider; direct root entry did not warn. Legacy link/LTO warning lines are preserved separately.',
  'sra01 preserves two unchanged synchronous-render timing threshold failures (0.7795494/0.8358071 seconds versus 0.75) while another owned backend compile ran. Final complete async repeat is serial after all owned compile sequences finish; thresholds/test body are unchanged. Concurrent unrelated compile load is not a guaranteed timing environment.',
  'No hardware, publication, merge, push, tag, FINAL, math algorithms, UI layout, GSHC or FLP changes.'
 ]}
(task/'SCG_FREEZE_CONTRACT_REPAIR_20261010.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps({'totals':data['totals'],'gates':len(gates),'gate_exits':[row.get('exit') for row in gates],
 'daily':data['daily'],'ccdi':data['ccdi']},indent=2))
