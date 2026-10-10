from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess,re
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar');code='e1357b417ee98df5990a1fff18c55d6b35183896'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
assert not subprocess.check_output(['git','-C',str(repo),'diff'],text=True)
archive=repo/'apps/SCG/docs/evidence/native_usb_local_merge_20261010';assert not archive.exists();archive.mkdir(parents=True)
(archive/'.gitattributes').write_bytes(b'* -text\n')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(p,relative):
    p=Path(p);dest=archive/relative;dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists(),relative;dest.write_bytes(p.read_bytes())
def tree(root,relative):
    for p in sorted(Path(root).rglob('*')):
        if p.is_file():copy(p,relative+'/'+p.relative_to(root).as_posix())
record={'tested_daily_code_commit':code,'merge_commit':'2016a1279fa529c96d5b108d7d67326e2fda3653',
 'accepted_source_code_commit':'f61cbd851b8ac32b865deb1a3997058685dfebbd','accepted_source_evidence_commit':'5b99438ba4005ea02935e9734307e749e2e758e7',
 'created_utc':datetime.now(timezone.utc).isoformat(),'formal_release':False,'independent_usb_safety_review':'NO_PASSED_OUTCOME',
 'normal_tests':{},'history':{},'builds':[],'hardware_actions':False,'push_or_publish':False}
for label,count in [('dm02',12),('dmr02',99),('dma01',16),('dmg03',5)]:
    d=json.loads((task/(label+'-command.json')).read_text());log=(task/(label+'.log')).read_text(encoding='utf8')
    assert d['source_commit']==code and d['exit']==0 and not d.get('dirty_diff',''),label
    assert int(re.findall(r'(\d+) passed',log)[-1])==count and not re.search(r'\d+ (?:failed|error|skipped)',log),label
    record['normal_tests'][label]={'passed':count,'scope':d['scope'],'deselected':45 if label=='dmg03' else 0,'skipped':0}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'runs/'+p.name)
for label in ['dm01','dmr01','dmg01','dmg02']:
    d=json.loads((task/(label+'-command.json')).read_text());record['history'][label]={'exit':d['exit'],'source_commit':d['source_commit']}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'history/'+p.name)
for name in ['usb-daily-merge-preflight.json','usb-daily-merge-receipt.json','usb-daily-merge.log','daily-pinned-byte-audit.json',
 'daily-f103-authority-identity.json','daily-radio-delivery-fix.json','daily-before-sx1281_device.c.bin','daily-before-sx1280-hal.c.bin',
 'daily-scg-startup-before-delivery.json','daily-scg-startup.json','daily-scg-launcher.json','daily-scg-startup-restricted-failure.log']:
    p=task/name
    if p.is_file():copy(p,'delivery/'+name)
startup=json.loads((task/'daily-scg-startup.json').read_text());assert startup['source_commit']==code and startup['exit']==0 and not startup['errors']
record['startup']=startup
gates=json.loads((task/'dmgates01-gates.json').read_text());assert len(gates)==8 and all(g['exit']==0 for g in gates)
record['emitted_gates']=gates;copy(task/'dmgates01-gates.json','runs/dmgates01-gates.json')
for p in task.glob('dmgates01-*.log'):copy(p,'runs/'+p.name)
for label in ['dm02','dma01']:
    for p in Path('C:/Users/chdxm/AppData/Local/Temp/'+label).rglob('*'):
        if p.is_file() and p.name in ['worker-durations.json','refresh-response.json','build-responsiveness.json']:
            copy(p,'response/'+label+'/'+p.parent.name+'/'+p.name)
            if p.name in ['refresh-response.json','build-responsiveness.json']:record.setdefault(p.stem,[]).append(json.loads(p.read_text()))
rows=[json.loads(x) for x in (task/'dm02-build-index.jsonl').read_text().splitlines()]
assert {r['part'] for r in rows}=={'STM32F103C8T6','STM32C071FBP6'}
for row in rows:
    root=Path(row['output']);part=row['part'];project=Path(row['project_root'])
    receipt=json.loads((root/'receipt.json').read_text());backend=json.loads((root/'backend-receipt.json').read_text());snapshot=json.loads((root/'source-snapshot.json').read_text())
    pointer=json.loads((project/'.fccg/usb-candidate.json').read_text());model=project/'SilverStar.ssproject'
    assert receipt['source_commit']==snapshot['source_commit']==code and receipt['auditable_dirty_diff']==snapshot['dirty_diff']==''
    assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert len(receipt['commands'])==receipt['planned_command_total'] and all(c['exit']==0 for c in receipt['commands']) and receipt['warning_diagnostics']==[]
    assert any('-fanalyzer' in c['command'] for c in receipt['commands']) and not any('-fsyntax-only' in c['command'] for c in receipt['commands'])
    assert sha(model)==sha(root/'candidate_config.ssproject')==receipt['runtime_project_sha256']
    assert backend['model_sha256']==receipt['runtime_model_sha256']==pointer['model_sha256']
    assert backend['compile_receipt_sha256']==sha(root/'receipt.json') and row['backend_receipt_sha256']==pointer['backend_receipt_sha256']==sha(root/'backend-receipt.json')
    assert pointer['result']=='CompiledCandidate' and pointer['formal_release'] is False
    for p,digest in {**receipt['experimental_files_sha256'],**receipt['output_artifact_sha256']}.items():assert sha(root/p)==digest,(part,p)
    prefix='HardwareGenerated/STM32CubeMX/' if part=='STM32C071FBP6' else 'HardwareGenerated/NativeClassicCdc/'
    for p,digest in receipt['input_sha256'].items():assert sha(root/(prefix+p))==digest,(part,p)
    for name,item in snapshot['modules'].items():assert sha(repo/'apps/SCG'/name)==item['sha256'],name
    quality=json.loads((root/'.fccg/quality-results.json').read_text());assert set(quality['results'])=={'architecture_check','artifact_check'} and all(v['result']=='passed' for v in quality['results'].values())
    record['builds'].append({'part':part,'output':str(root),'project_root':str(project),'commands':len(receipt['commands']),
      'source_snapshot_sha256':sha(root/'source-snapshot.json'),'source_snapshot_modules':len(snapshot['modules']),
      'compiler_receipt_sha256':sha(root/'receipt.json'),'backend_receipt_sha256':sha(root/'backend-receipt.json'),
      'model_sha256':receipt['runtime_model_sha256'],'toolchain_version':receipt['toolchain_version'],
      'elf_sha256':{p:sha(root/p) for p in ['build/native.elf','build/analysis/native.elf']},'irq_header_sha256':receipt['facts']['irq_header_sha256'],
      'gui_quality':quality['results'],'generated_files':len(receipt['experimental_files_sha256']),'native_inputs':len(receipt['input_sha256'])})
    tree(project,'final/'+part+'/saved_project')
    selected=set(receipt['experimental_files_sha256'])|{'Makefile','receipt.json','backend-receipt.json','backend-owner.json','candidate_config.ssproject','commands.log','source-snapshot.json'}
    for f in root.rglob('*'):
        if not f.is_file():continue
        relative=f.relative_to(root).as_posix()
        if relative in selected or relative.startswith(('.fccg/','Tools/','Evidence/')) or (relative.startswith('build/') and f.suffix in ['.elf','.map','.su','.bin']):copy(f,'final/'+part+'/'+relative)
review=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-09\task-2\gui-f61-review')
for name in ['review.md','scope-audit.json','receipt-audit.json','independent-async.json','independent-late-callbacks.json']:
    if (review/name).is_file():copy(review/name,'accepted-ordinary-review/'+name)
for name in ['merge_usb_candidate_daily.py','prepare_daily_validation.py','daily_backend_pytest.py','run_daily_usb_gui.py','run_daily_regression.py','run_daily_async.py',
 'daily_formal_gate_check.py','daily_scg_startup_check.py','inspect_daily_pinned_bytes.py','audit_daily_f103_authority_identity.py','pin_daily_native_radio_delivery.py',
 'run_usb_candidate_gates.py','package_daily_merge_verification.py','record_daily_launcher.py','write_daily_merge_report.py',
 'stage_verify_daily_merge_evidence.py','commit_daily_merge_evidence.py']:
    copy(task/name,'runners/'+name)
for path in ['apps/SCG/.gitattributes','apps/SCG/src/silverstar_fccg/generator/native_radio.py',
 'apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload/Devices/Telemetry/SX1281/Src/sx1281_device.c',
 'apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload/Middlewares/Third_Party/SX1280lib/sx1280-hal.c']:
    copy(repo/path,'owning-source/'+path.removeprefix('apps/SCG/'))
preflight=json.loads((task/'usb-daily-merge-preflight.json').read_text());record['preserved_untracked_sha256']=preflight['preserved_untracked_sha256']
for p,digest in record['preserved_untracked_sha256'].items():assert sha(repo/p)==digest
record['backup_ref']=preflight['backup_ref'];record['daily_branch']=subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()
record['remaining_scope']='Explicit exact-target software candidate. Synchronous view fill and pinned SDK/worktree evidence dependencies remain. Extra generic-to-pinned F103 equality test fails because its evidence descriptor identity differs; data/CPU/memory/IRQ facts otherwise equal. No formal/hardware/safety release.'
record['files_sha256']={p.relative_to(archive).as_posix():sha(p) for p in sorted(archive.rglob('*')) if p.is_file()};record['listed_bytes']=sum((archive/p).stat().st_size for p in record['files_sha256'])
(archive/'verification.json').write_text(json.dumps(record,indent=2),encoding='utf8',newline='\n')
summary={k:record[k] for k in ['tested_daily_code_commit','merge_commit','accepted_source_code_commit','accepted_source_evidence_commit','normal_tests','builds','refresh-response','build-responsiveness','backup_ref','daily_branch']}
summary.update(listed_files=len(record['files_sha256']),listed_bytes=record['listed_bytes'],manifest_sha256=sha(archive/'verification.json'))
(task/'daily-merge-verification-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary,indent=2))
