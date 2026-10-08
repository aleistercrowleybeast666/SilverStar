from pathlib import Path
import json, hashlib, shutil, subprocess, datetime, sys, re
root=Path(__file__).resolve().parent; repo=root.parents[1]
formal=repo/'docs/evidence/static_log_file_20261008'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def copy(source,relative):
    target=formal/relative
    assert source.is_file() and not target.exists()
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    assert sha(source)==sha(target)

assert not formal.exists(), 'Preserve existing formal evidence'
old=json.loads((repo/'docs/evidence/static_bench_repeat_20261008/manifest.json').read_text())
expected=json.loads((repo/'docs/evidence/static_bench_repeat_20261008/source_apps_sha256.json').read_text())
actual={name:sha(repo/name) for name in expected}
assert actual==expected, 'Application source changed'
user_inputs={name:sha(repo/name) for name in old['root_inventory_inputs_preserved']}
assert user_inputs==old['root_inventory_inputs_preserved']
inventory=json.loads((root/'input_inventory.json').read_text())
assert sha(Path(inventory['archive']))==inventory['archive_sha256']
assert sha(Path(inventory['decoder']['path']))==inventory['decoder']['sha256']
test=json.loads((root/'focused_test_result_v4.json').read_text())
assert test['exit']==0
log=(root/'focused_regressions_v4.log').read_text(encoding='utf-8-sig')
assert '38 passed in 151.88s' in log
assert json.loads((root/'qt_messages_v2.json').read_text())==[]
formal.mkdir(parents=True)
for row in inventory['members']:
    p=Path(row['snapshot_path']); assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    copy(p,Path('inputs')/row['source_member'])
copy(Path(inventory['decoder']['path']),Path('inputs')/'KF6_Static_20261008_f045d8c.ssdecoder')
names=['input_inventory.json','inspect_logs.py','inspect_runner.log','prepare_sidecar_audit.py',
       'audit_sidecars.py','gui_roundtrip.py','gui_roundtrip_v2.py','gui_runner.log','gui_runner_v2.log',
       'gui_failure.json','gui_progress.json','gui_progress_v2.json','qt_messages.json','qt_messages_v2.json',
       'continuity_audit.py','continuity_runner.log','focused_regressions.py','focused_regressions_v2.py',
       'focused_regressions_v3.py','focused_regressions_v4.py','focused_regressions.log',
       'focused_regressions_v2.log','focused_regressions_v3.log','focused_regressions_v4.log',
       'focused_test_result_v2.json','focused_test_result_v4.json','pytest_v2.xml','pytest_v4.xml',
       'focused_regressions_v2.exit.txt','focused_regressions_v3.exit.txt','focused_regressions_v4.exit.txt',
       'package_evidence.py']
for name in names:copy(root/name,Path('execution')/name)
copy(repo/'.work/nightly_closeout_20261008/normal_test_paths.py',Path('execution')/'normal_test_paths.py')
for mission in (44,45):
    for name in ['parse_summary.json','record_samples.json','critical_records.json',
                 'health_field_summary.json','sidecar_audit.json','sidecar_runner.log','continuity_audit.json']:
        copy(root/f'm{mission}'/name,Path('results')/f'm{mission}'/name)
    for name in ['gui_result.json','overview.png','flight.png','estimation.png']:
        copy(root/f'p{mission}_v2'/name,Path('results')/f'p{mission}'/name)
projects={}
for mission in (44,45):
    folder=root/f'p{mission}_v2'
    projects[str(mission)]={str(p.relative_to(folder)):{'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in folder.rglob('*') if p.is_file() and (p.suffix=='.ssflp' or '.artifacts' in str(p))}
write(formal/'project_artifact_hashes.json',projects)
write(formal/'source_apps_sha256.json',actual)
commands=[
 {'command':'.venv/Scripts/python.exe .work/flp08tf/inspect_logs.py','exit':0,'scope':'Selected 20 ZIP members + strict production parse'},
 {'command':'.venv/Scripts/python.exe .work/flp08tf/audit_sidecars.py 44','exit':0},
 {'command':'.venv/Scripts/python.exe .work/flp08tf/audit_sidecars.py 45','exit':0},
 {'command':'.venv/Scripts/python.exe -X faulthandler .work/flp08tf/gui_roundtrip.py','exit':1,'scope':'NumPy 2.4.0 safety rejection, zero runs; not native crash'},
 {'command':'apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/gui_roundtrip_v2.py','exit':0,'scope':'Same native Windows process actual 44/45, all 2+2 runs and strict GUI reopen'},
 {'command':'apps/FLP/.venv/Scripts/python.exe .work/flp08tf/continuity_audit.py','exit':0},
 {'command':'apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/focused_regressions.py','exit':1,'scope':'38 fixture setup errors, pytest mode0700 directory unreadable'},
 {'command':'apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/focused_regressions_v2.py','exit':1,'scope':'17 pass / 21 missing qtbot fixture errors'},
 {'command':'apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/focused_regressions_v3.py','exit':1,'scope':'Duplicate pytest-qt registration before collection'},
 {'command':'apps/FLP/.venv/Scripts/python.exe -X faulthandler .work/flp08tf/focused_regressions_v4.py','exit':0,'scope':'One complete same-process 38 pass, 151.88s; tiny fixtures'}]
files={str(p.relative_to(formal)):{'bytes':p.stat().st_size,'sha256':sha(p)}
       for p in formal.rglob('*') if p.is_file()}
manifest={'starting_document_HEAD':inventory['repository_HEAD'],'source_commit':'cac7bd29bf6f6aec5297715ea14893b4b7684953',
    'branch':subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip(),
    'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_files':len(actual),'source_matches_previous_snapshot':True,'root_inventory_inputs_preserved':user_inputs,
    'archive':inventory['archive'],'archive_sha256':inventory['archive_sha256'],
    'archive_bytes':inventory['archive_bytes'],'selected_members':20,'selected_inputs_and_decoder_preserved':True,
    'commands':commands,'test_environment':test,'gui_qt_messages':[],
    'projects_retained_at':[str(root/f'p{m}_v2'/f'mission{m}.ssflp') for m in (44,45)],
    'source_hardware_identity':'Prior authorized bench 44/45 actual cac7bd2 BIN/readback; no hardware in this stage',
    'remaining_NOT_PROVEN':['Rejected push call identity and safety impact','End-to-end radio delivery',
        'Boot maximum interval attribution','Navigation accuracy / MCU WCET / full stack proof / critical manual review'],
    'historical_FAIL_preserved':['Unattributed Qt/Shiboken native abort in earlier combined suite'],
    'NOT_RUN':['Unrelated archive member scan','Long log/ESKF15/full prior suite rerun','Any hardware action'],
    'files':files}
write(formal/'manifest.json',manifest)
print(json.dumps({'formal_files':len(files)+1,'formal_bytes':sum(r['bytes'] for r in files.values()),
                  'source_files_unchanged':len(actual),'user_inputs_unchanged':len(user_inputs)},indent=2))
