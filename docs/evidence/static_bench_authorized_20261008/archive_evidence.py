"""Archive only this completed run's bounded evidence; never change originals."""
from pathlib import Path
import hashlib, json, subprocess, re
from datetime import datetime, timezone

out = Path(__file__).resolve().parent
repo = out.parents[1]
dest = repo/'docs/evidence/static_bench_authorized_20261008'
assert not (dest/'manifest.json').exists(), 'Refuse overwrite completed formal evidence'
dest.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
base = json.loads((repo/'docs/evidence/static_bench_20261008/source_apps_sha256.json').read_text(encoding='utf-8'))
current = {p: sha(repo/p) for p in base}
changed = [p for p in base if current[p] != base[p]]
expected = 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py'
assert changed == [expected], changed
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip() == 'cac7bd29bf6f6aec5297715ea14893b4b7684953'
inventory = ['work_build_candidates_20261006.csv','work_inventory_20261006.txt','work_subtree_classification_20261006.csv']
old = json.loads((repo/'docs/evidence/static_bench_20261008/manifest.json').read_text(encoding='utf-8'))
roots = {p:sha(repo/p) for p in inventory}
assert roots == old['root_inventory_inputs_preserved']
artifacts = json.loads((out/'flash_result.json').read_text(encoding='utf-8'))
assert artifacts['exit_code'] == 0 and artifacts['exact_readback_match']
for item in artifacts['artifacts'].values():
    assert sha(Path(item['path'])) == item['sha256'], item
for step in ('versions','architecture','power10','release','analyzer','host'):
    r=json.loads((out/(step+'_result.json')).read_text(encoding='utf-8'))
    assert r['exit_code'] == 0 and sha(out/(step+'.log')) == r['log_sha256']
    assert r['source_commit'] == artifacts['source_commit'] and not r['tracked_status']
mission=json.loads((out/'mission_static_01/result.json').read_text(encoding='utf-8'))
assert mission['mission_result'] == 'COMPLETED_OBSERVED_SEQUENCE'
assert all(mission['functional_checks'].values())
assert mission['final_diagnostics']['decoded']['mission_id']['value'] == 44
assert 'RESUMED_AFTER_COHERENT_CAPTURE' in (out/'diag_postmission/openocd.log').read_text(encoding='utf-8')
retained = []
files = []
for p in sorted(out.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts:
        continue
    relative = p.relative_to(out)
    if relative.parts[0] == 'unknown_source_negative':
        continue
    record={'path':relative.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
    if relative.as_posix() in ('current_F407_before_test_fullflash.bin','flashed_image_readback.bin'):
        record['retained_path']=str(p)
        retained.append(record)
    else:
        target=dest/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and relative.as_posix() != 'archive_evidence.py':
            assert sha(target) == record['sha256'], 'Existing raw evidence differs'
        else:
            target.write_bytes(p.read_bytes())
        assert sha(target)==record['sha256']
        files.append(record)
(dest/'.gitattributes').write_text('* -text\n',encoding='ascii')
(dest/'source_apps_sha256.json').write_text(json.dumps(current,indent=2),encoding='utf-8')
files.append({'path':'source_apps_sha256.json','bytes':(dest/'source_apps_sha256.json').stat().st_size,'sha256':sha(dest/'source_apps_sha256.json')})
doc = repo/'docs/STATIC_BENCH_ACCEPTANCE_20261008.md'
links=[]
for link in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
    if ':' in link or link.startswith('#'):
        continue
    target=(doc.parent/link.split('#')[0]).resolve()
    links.append({'link':link,'exists':target.exists() or target == dest/'manifest.json'})
assert all(x['exists'] for x in links), links
manifest={
    'source_commit':artifacts['source_commit'],'branch':'fix/nightly-user-ready-20261003',
    'recorded_utc':datetime.now(timezone.utc).isoformat(),'source_file_count':len(current),
    'source_delta_from_f045d8c':changed,'root_inventory_inputs_preserved':roots,
    'actual_run':{'flash_exit_code':0,'readback_match':True,'static_script_exit_code':0,
        'mission_id':44,'start_count':1,'command_retries':0,'ground_reflash':False,
        'critical_contract_review':'NOT_PROVEN','actual_TF_contents':'NOT_PROVEN',
        'FLP_actual_recorded_open_save_reopen':'NOT_RUN','logger_state_reject_attribution':'NOT_PROVEN',
        'radio_tx_dropped_attribution':'NOT_PROVEN','scheduler_max_interval_attribution':'NOT_PROVEN'},
    'files':files,'retained_work_artifacts':retained,'artifact_identity':artifacts['artifacts'],
    'doc_links':links,
    'record_limitations':['Formal manifest created after execution; static script exit0 independently observed by exec session 73259, not an execution timestamp invented later.','Full original firmware backup, fresh BIN/ELF/decoder/config/readback remain at recorded .work paths; no vendor tree copied.','Serial acquisition and SWD runtime observations do not establish persistent TF bytes.','Historical preparation exit2 and prior test setup errors remain in separate immutable reports.']}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'files':len(files),'source_count':len(current),'source_changed':changed,'links':len(links),'all_links_exist':True},indent=2))
