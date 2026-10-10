from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess

task=Path(__file__).resolve().parent
root=Path(r'D:\python_software\SilverStar\.work\ccdi')
code=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert code=='efef41f49c451ba38b4b7ca88581d4e89b6ee23d'
destination=task/'usb-first-batch-binding-evidence'
assert not destination.exists()
destination.mkdir()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(source,relative):
    target=destination/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)

changed=subprocess.check_output(['git','-C',str(root),'diff','--name-only',
    'ed9ff651f0b6d8483378889009811ab572dff109',code],text=True).splitlines()
sources={}
for path in changed:
    body=subprocess.check_output(['git','-C',str(root),'show',code+':'+path])
    actual=(root/path).read_bytes()
    assert body==actual or body==actual.replace(b'\r\n',b'\n')
    sources[path]={'working_sha256':digest(root/path),'git_blob_sha256':hashlib.sha256(body).hexdigest()}
    copy(root/path,Path('source')/path)
for label in ['ub01','ub02','ub03','ub04','ubr01']:
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        source=task/(label+suffix)
        if source.exists(): copy(source,'attempts/'+source.name)
for source in task.glob('ub03-f103-*.log'): copy(source,'gates/'+source.name)
for name in ['ub03-gates.json','usb-wheel.json','usb-wheel.log']:
    copy(task/name,'checks/'+name)
for name in ['prepare_usb_targets.py','install_usb_backend.py','include_usb_profile_data.py',
    'backend_pytest.py','run_usb_backend_tests.py','run_backend_tests.py',
    'run_backend_regressions.py','run_usb_preserved_regressions.py',
    'run_backend_gates.py','run_usb_f103_gates.py','build_usb_backend_wheel.py',
    'package_usb_binding_evidence.py']:
    copy(task/name,'runners/'+name)
for label in ['ub03','ub04']:
    recorded=json.loads((task/(label+'-command.json')).read_text(encoding='utf-8'))
    rows=recorded.get('sources', recorded.get('source_sha256'))
    for path,value in rows.items():
        expected=value['sha256'] if isinstance(value,dict) else value
        assert digest(root/path)==expected
builds=[]
for label in ['ub03','ub04']:
    for row in [json.loads(line) for line in (task/(label+'-build-index.jsonl')).read_text().splitlines()]:
        output=Path(row['output'])
        receipt=json.loads((output/'receipt.json').read_text(encoding='utf-8'))
        backend=json.loads((output/'backend-receipt.json').read_text(encoding='utf-8'))
        artifacts=receipt['output_artifact_sha256']
        assert all(digest(output/path)==value for path,value in artifacts.items())
        assert backend['model_sha256']==receipt['runtime_model_sha256']
        assert backend['compile_receipt_sha256']==digest(output/'receipt.json')
        assert all(item['exit']==0 for item in receipt['commands'])
        assert receipt['warning_diagnostics']==[]
        name=label+'-'+row['part']
        for path in ['receipt.json','backend-receipt.json','source-snapshot.json','commands.log',
            'candidate_config.ssproject','Makefile','Generated/ground_source_graph.json',
            'Generated/native_ground_contract.json','build/native.elf','build/native.map',
            'build/analysis/native.elf','build/analysis/native.map']:
            copy(output/path,Path('builds')/name/path)
        for source in (output/'build/native-host').glob('*'):
            if source.is_file(): copy(source,Path('builds')/name/'build/native-host'/source.name)
        copy(Path(row['project'])/'SilverStar.ssproject',Path('builds')/name/'saved-project.ssproject')
        builds.append({'label':label,'part':row['part'],'actual_output':str(output),
            'commands':len(receipt['commands']),'compiler_warnings':receipt['warning_diagnostics'],
            'recorded_artifact_hashes_checked':len(artifacts),
            'model_sha256':backend['model_sha256'],'elf_sha256':digest(output/'build/native.elf'),
            'scope':receipt['validation_scope']})
wheel=json.loads((task/'usb-wheel.json').read_text())
copy(Path(wheel['wheel']),'package/'+Path(wheel['wheel']).name)
native_profile=json.loads((root/'apps/SCG/src/silverstar_fccg/hardware/usb_profiles/c071-native-profile.json').read_text())
native=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-08\task\c071-cubemx-input\full-native-clean\C071FBP6_PCD_TEST')
expected=dict(native_profile['files_sha256'])
expected.update({'C071FBP6_PCD_TEST.ioc':native_profile['ioc_sha256'],'Makefile':native_profile['makefile_sha256'],
    'startup_stm32c071xx.s':native_profile['startup_sha256'],'STM32C071XX_FLASH.ld':native_profile['linker_sha256']})
assert all(digest(native/p)==value for p,value in expected.items())
summary={'schema_version':1,'source_commit':code,'tested_base':'ed9ff651f0b6d8483378889009811ab572dff109',
    'tested_snapshot':'Auditable dirty source captured by ub03/ub04, raw working hashes matched code commit; no claim of post-commit rebuild',
    'source_modules':sources,'builds':builds,
    'c071_original_native_files_hashes_checked_after_tests':len(expected),
    'c071_current_firmware_build':'NOT EXECUTED: renderer/build integration not implemented in unified backend',
    'c071_usb_review':'No passed outcome for b66; stopped review not retried or bypassed',
    'tests':{'ub01':'1 failed,18 passed; test reload cache configuration mismatch; retained',
        'ub02':'19 passed; intermediate version, not final full suite',
        'ub03':'21 passed,0 skipped;100.13s; includes actual F103 unified ARM/analyzer Build',
        'ub04':'28 passed,0 skipped;241.12s; retained private F103/F407 backend tests and two real builds',
        'ubr01':'11 passed;22.80s; separate preserved import/model/build-tooling unit regressions'},
    'warnings':'Each pytest suite has one existing Unknown config option: cache_dir warning; ARM compilation had none',
    'gates':json.loads((task/'ub03-gates.json').read_text()),
    'package':wheel,
    'shell_prep_failure':'One inline command for preserved regressions had quoting SyntaxError before tests; replaced by saved runner, not counted as PASS',
    'publication':'BLOCKED; partial software integration only; no GUI, hardware, daily merge or push',
    'remaining':{'ordinary_implementation':'C071 firmware renderer and shared compiler integration pending; F103 shared EP0 repair not integrated',
        'acceptance':'Complete EP0/async lifecycle/control/reset/config/deinit/cancel ownership, manual critical-contract, libraries/indirect calls/recursion and MSP/ISR stack/WCET NOT PROVEN',
        'hardware':'No physical USB/SPI/radio/IRQ/timing/stack high-water validation'},
    'finished_utc':datetime.now(timezone.utc).isoformat()}
(destination/'checks/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(destination).as_posix():digest(p) for p in destination.rglob('*') if p.is_file()}
manifest={'source_commit':code,'files_sha256':files,'listed_items':len(files),
    'manifest_not_included_in_list':True,'summary':'checks/summary.json'}
(destination/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'source_commit':code,'listed_items':len(files),'total_bytes':sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()),
    'manifest_sha256':digest(destination/'verification.json'),'builds':builds},indent=2))
