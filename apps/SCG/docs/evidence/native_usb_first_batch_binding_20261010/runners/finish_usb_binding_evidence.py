from pathlib import Path
import hashlib, json, shutil

task=Path(__file__).resolve().parent
evidence=task/'usb-first-batch-binding-evidence'
temp=Path(r'C:\Users\chdxm\AppData\Local\Temp\ub03')
models=[]
for path in sorted(temp.glob('p_*/SilverStar.ssproject')):
    data=json.loads(path.read_text(encoding='utf-8'))
    hw=data.get('ground_target',{}).get('hardware',{})
    if hw.get('mcu') != 'STM32C071FBP6': continue
    destination=evidence/'c071-models'/path.parent.name
    destination.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,destination/'SilverStar.ssproject')
    identity=hw['snapshot_id']
    candidates=list(temp.glob('u_*/i/'+identity+'/usb-ground-contract.json'))
    assert candidates
    contract=None
    for candidate in candidates:
        proof=json.loads(candidate.read_text(encoding='utf-8'))
        snapshot=candidate.parent/'UsbGroundNative'
        if all(hashlib.sha256((snapshot/p).read_bytes()).hexdigest()==value
               for p,value in proof['native_files_sha256'].items()):
            contract=candidate
            break
    assert contract is not None
    shutil.copyfile(contract,destination/'usb-ground-contract.json')
    models.append({'model':str(path),'backend_workspace':str(contract.parents[2]),
        'backend_cache':str(contract.parents[1]),'snapshot_id':identity,
        'model_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
assert models
(evidence/'c071-models/index.json').write_text(json.dumps(models,indent=2)+'\n',encoding='utf-8')
summary=json.loads((evidence/'checks/summary.json').read_text(encoding='utf-8'))
summary['c071_saved_models']=models
(evidence/'checks/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(Path(__file__),evidence/'runners'/Path(__file__).name)
files={p.relative_to(evidence).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in evidence.rglob('*') if p.is_file() and p.name!='verification.json'}
manifest={'source_commit':summary['source_commit'],'files_sha256':files,'listed_items':len(files),
    'manifest_not_included_in_list':True,'summary':'checks/summary.json'}
(evidence/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'models':len(models),'listed_items':len(files),'manifest_sha256':hashlib.sha256((evidence/'verification.json').read_bytes()).hexdigest(),
    'c071_native_files_checked':summary['c071_original_native_files_hashes_checked_after_tests']}))
