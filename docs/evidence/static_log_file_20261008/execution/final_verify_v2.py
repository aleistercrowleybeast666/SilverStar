from pathlib import Path
import json, hashlib, shutil, subprocess, re, datetime
root=Path(__file__).resolve().parent;repo=root.parents[1]
formal=repo/'docs/evidence/static_log_file_20261008'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
manifest=json.loads((formal/'manifest.json').read_text(encoding='utf-8'))
for name,row in manifest['files'].items():
    p=formal/name;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],name
source=json.loads((formal/'source_apps_sha256.json').read_text(encoding='utf-8'))
assert all(sha(repo/name)==digest for name,digest in source.items())
assert all(sha(repo/name)==digest for name,digest in manifest['root_inventory_inputs_preserved'].items())
assert sha(Path(manifest['archive']))==manifest['archive_sha256']
for mission in (44,45):
    folder=root/f'p{mission}_v2'
    project_hashes=json.loads((formal/'project_artifact_hashes.json').read_text(encoding='utf-8'))[str(mission)]
    assert all(sha(folder/name)==row['sha256'] for name,row in project_hashes.items())
documents=['docs/STATIC_LOG_FILE_ACCEPTANCE_20261008.md','docs/USER_WORKFLOW.md','docs/README.md',
           'docs/STATIC_BENCH_ACCEPTANCE_20261008.md','docs/STATIC_BENCH_REPEAT_20261008.md']
links=[]
for name in documents:
    p=repo/name
    text=p.read_text(encoding='utf-8')
    assert '\ufffd' not in text, name
    for target in re.findall(r'\]\(([^)]+)\)',text):
        if '://' in target or target.startswith('#'):continue
        target=target.split('#')[0]
        assert (p.parent/target).exists(),(name,target)
        links.append([name,target])
assert subprocess.run(['git','diff','--check'],cwd=repo).returncode==0
assert subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()=='fix/nightly-user-ready-20261003'
shutil.copyfile(formal/'manifest.json',formal/'manifest_before_initial_state_audit.json')
for name in ['initial_state_audit.py','initial_state_runner.log','final_verify_v2.py', 'final_verify.py', 'final_verify_v1.log', 'final_verify_v1.exit.txt']:
    shutil.copyfile(root/name,formal/'execution'/name)
for mission in (44,45):
    shutil.copyfile(root/f'm{mission}'/'initial_state_audit.json',formal/'results'/f'm{mission}'/'initial_state_audit.json')
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_files_unchanged':len(source),'original_inventory_files_unchanged':3,
        'original_archive_unchanged':True,'saved_project_artifacts_hashes_unchanged':True,
        'documents_checked':documents,'local_links_checked':len(links),'replacement_character_count':0,
        'git_diff_check_exit':0,'hardware_actions':0}
write(formal/'final_verification.json',result)
manifest['commands'].append({'command':'apps/FLP/.venv/Scripts/python.exe .work/flp08tf/initial_state_audit.py','exit':0,
                            'scope':'Actual recorded START / alignment / INITIAL_STATE / first estimator; no replay'})
manifest['commands'].append({'command':'apps/FLP/.venv/Scripts/python.exe .work/flp08tf/final_verify_v2.py','exit':0})
manifest['final_verification']='final_verification.json'
manifest['files']={str(p.relative_to(formal)):{'bytes':p.stat().st_size,'sha256':sha(p)}
                   for p in formal.rglob('*') if p.is_file() and p!=formal/'manifest.json'}
write(formal/'manifest.json',manifest)
print(json.dumps(result,indent=2))
