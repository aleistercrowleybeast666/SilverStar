from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess,re
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
code='f61cbd851b8ac32b865deb1a3997058685dfebbd'
baseline='bf22bdcd56e76687e8be40d5f221cb3c29668ec1'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
assert not subprocess.check_output(['git','-C',str(repo),'diff'],text=True)
archive=repo/'apps/SCG/docs/evidence/native_usb_gui_async_20261010'
assert not archive.exists(), 'Never replace an existing evidence archive'
archive.mkdir(parents=True);(archive/'.gitattributes').write_bytes(b'* -text\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(p,relative):
    p=Path(p);dest=archive/relative;dest.parent.mkdir(parents=True,exist_ok=True)
    assert not dest.exists(),relative
    dest.write_bytes(p.read_bytes())
def tree(root,relative):
    for p in sorted(Path(root).rglob('*')):
        if p.is_file():copy(p,relative+'/'+p.relative_to(root).as_posix())
record={'code_commit':code,'previous_accepted_evidence_commit':baseline,'created_utc':datetime.now(timezone.utc).isoformat(),
 'formal_release':False,'independent_usb_safety_review':'NO_PASSED_OUTCOME; stopped b66 review not retried, bypassed, or labelled passed',
 'normal_tests':{},'builds':[],'history':{},'hardware_actions':False,'push_or_merge':False}
for label,count in [('ua04',12),('ur06',16),('ugr04',99),('ul19',2)]:
    d=json.loads((task/(label+'-command.json')).read_text(encoding='utf8'))
    log=(task/(label+'.log')).read_text(encoding='utf8')
    assert d['source_commit']==code and d['exit']==0 and not d.get('dirty_diff',''),label
    assert not re.search(r'\d+ (?:failed|error|skipped)',log) and int(re.findall(r'(\d+) passed',log)[-1])==count,label
    record['normal_tests'][label]={'passed':count,'skipped':0,'scope':d['scope']}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'runs/'+p.name)
for label in ['ua01','ua02','ua03','ur01','ur02','ur03','ur04','ur05','ugr03','ul18']:
    d=json.loads((task/(label+'-command.json')).read_text(encoding='utf8'))
    record['history'][label]={'exit':d['exit'],'source_commit':d['source_commit'],'dirty_snapshot_recorded':bool(d.get('dirty_diff',''))}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'history/'+p.name)
    for p in Path('C:/Users/chdxm/AppData/Local/Temp/'+label).rglob('*'):
        if p.is_file() and p.name in ['worker-durations.json','refresh-response.json','build-responsiveness.json']:
            copy(p,'history/'+label+'/'+p.relative_to(p.parents[1]).as_posix())
gates=json.loads((task/'uag01-gates.json').read_text(encoding='utf8'))
assert len(gates)==8 and all(g['exit']==0 for g in gates)
record['emitted_gate_commands']=gates;record['gate_command_count']=8
copy(task/'uag01-gates.json','runs/uag01-gates.json')
for p in task.glob('uag01-*.log'):copy(p,'runs/'+p.name)
responses=[]
for p in Path(r'C:\Users\chdxm\AppData\Local\Temp\ur06').rglob('refresh-response.json'):
    d=json.loads(p.read_text());assert d['plan_calls']==1 and d['plan_ran_off_gui_thread'] and d['ticks']>=10 and d['max_tick_gap_seconds']<.5
    responses.append(d);copy(p,'response/'+d['part']+'/refresh-response.json')
assert len(responses)==2;record['refresh_response']=responses
record['refresh_fixture_scope']='Read-only inspection of actual previous ug08 compiled legal candidates; unchanged original compiler/backend receipts and normal/analyzer ELF bytes asserted by fixture. Fresh ua04 builds separately test real buttons.'
for p in Path(r'C:\Users\chdxm\AppData\Local\Temp\ua04').rglob('worker-durations.json'):
    copy(p,'response/ua04/'+p.parent.name+'/worker-durations.json')
for p in Path(r'C:\Users\chdxm\AppData\Local\Temp\ua04').rglob('build-responsiveness.json'):
    d=json.loads(p.read_text());assert d['actual_enabled_build_button_clicked'] and d['ticks']>20 and d['max_tick_gap_seconds']<1
    record.setdefault('build_response',[]).append(d);copy(p,'response/'+d['part']+'/build-responsiveness.json')
assert len(record['build_response'])==2
for p in Path(r'C:\Users\chdxm\AppData\Local\Temp\ul19').glob('test_normal*/lifecycle-receipt.json'):
    d=json.loads(p.read_text());assert len(d['runs'])==17 and all(r['exit']==0 for r in d['runs'])
    record.setdefault('lifecycle_runs',[]).append(d);tree(p.parent,'host/'+d['part'])
assert len(record['lifecycle_runs'])==2
rows=[json.loads(x) for x in (task/'ua04-build-index.jsonl').read_text().splitlines()]
assert {r['part'] for r in rows}=={'STM32F103C8T6','STM32C071FBP6'}
for row in rows:
    root=Path(row['output']);part=row['part'];project=Path(row['project_root'])
    receipt=json.loads((root/'receipt.json').read_text());backend=json.loads((root/'backend-receipt.json').read_text())
    pointer=json.loads((project/'.fccg/usb-candidate.json').read_text());snapshot=json.loads((root/'source-snapshot.json').read_text())
    assert receipt['source_commit']==snapshot['source_commit']==code
    assert receipt['auditable_dirty_diff']==snapshot['dirty_diff']==''
    assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert len(receipt['commands'])==receipt['planned_command_total'] and all(c['exit']==0 for c in receipt['commands'])
    assert receipt['warning_diagnostics']==[] and any('-fanalyzer' in c['command'] for c in receipt['commands'])
    assert backend['model_sha256']==receipt['runtime_model_sha256']==pointer['model_sha256']
    assert backend['compile_receipt_sha256']==sha(root/'receipt.json')
    assert row['backend_receipt_sha256']==pointer['backend_receipt_sha256']==sha(root/'backend-receipt.json')
    assert pointer['output']==str(root) and pointer['result']=='CompiledCandidate' and pointer['formal_release'] is False
    runtime=project/'SilverStar.ssproject';assert sha(runtime)==sha(root/'candidate_config.ssproject')
    assert receipt['runtime_project']==str(runtime.resolve()) and receipt['runtime_project_sha256']==sha(runtime)
    for p,digest in {**receipt['experimental_files_sha256'],**receipt['output_artifact_sha256']}.items():assert sha(root/p)==digest,(part,p)
    prefix='HardwareGenerated/STM32CubeMX/' if part=='STM32C071FBP6' else 'HardwareGenerated/NativeClassicCdc/'
    for p,digest in receipt['input_sha256'].items():assert sha(root/(prefix+p))==digest,(part,p)
    quality=json.loads((root/'.fccg/quality-results.json').read_text())
    assert set(quality['results'])=={'architecture_check','artifact_check'} and all(v['result']=='passed' for v in quality['results'].values())
    record['builds'].append({'part':part,'output':str(root),'project_root':str(project),'model_sha256':receipt['runtime_model_sha256'],
      'runtime_project_sha256':sha(runtime),'source_snapshot_sha256':sha(root/'source-snapshot.json'),
      'compile_receipt_sha256':sha(root/'receipt.json'),'backend_receipt_sha256':sha(root/'backend-receipt.json'),
      'commands':len(receipt['commands']),'toolchain_version':receipt['toolchain_version'],
      'irq_header_sha256':receipt['facts']['irq_header_sha256'],
      'elf_sha256':{p:sha(root/p) for p in ['build/native.elf','build/analysis/native.elf']},
      'gui_quality':{a:{k:v[k] for k in ['duration','result','timestamp','command','input_sha256']} for a,v in quality['results'].items()},
      'native_input_files':len(receipt['input_sha256']),'generated_files':len(receipt['experimental_files_sha256']),'recorded_artifacts':len(receipt['output_artifact_sha256'])})
    tree(project,'final/'+part+'/saved_project')
    for f in root.rglob('*'):
        if not f.is_file():continue
        relative=f.relative_to(root).as_posix()
        keep=(relative.startswith(('Generated/','Common/','Ground/','Devices/','Interfaces/','Tests/','Platform/','HardwareGenerated/Reviewed','HardwareGenerated/C071ClassicCDC/','Middlewares/Reviewed','Tools/','.fccg/','Evidence/')) or
          relative in ['Makefile','receipt.json','backend-receipt.json','backend-owner.json','candidate_config.ssproject','commands.log','source-snapshot.json'] or
          (relative.startswith('build/') and (f.suffix in ['.elf','.map','.su','.bin'] or '/host/' in relative)))
        if keep:copy(f,'final/'+part+'/'+relative)
review=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-09\task-2\gui-63771a1-review')
for p in ['review.md','reproduce_refresh.py','ordinary-offscreen-refresh.json','ordinary-read-timing.json','archive-audit.json','audit-initial.json','independent-lifecycle/evidence.json']:
    if (review/p).is_file():copy(review/p,'parent-ordinary-review/'+p)
record['parent_review_scope']='Read-only previous ordinary GUI P2 reproduction/archive/lifecycle findings; no new independent safety review or execution of the stopped b66 attempt'
copy(task/'usb-async-visual-boundary.json','visual/source-boundary.json')
for folder in ['usb-async-visual-settled','usb-async-visual-isolated']:tree(task/folder,'visual/'+folder)
record['visual_scope']={'source_boundary':json.loads((task/'usb-async-visual-boundary.json').read_text()),
 'same_process_render':json.loads((task/'usb-async-visual-settled/receipt.json').read_text()),
 'separate_process_render':json.loads((task/'usb-async-visual-isolated/receipt.json').read_text())}
for name in ['package_usb_async_evidence.py','run_usb_gui_tests.py','run_usb_async_tests.py','run_gui_preserved_regression.py','run_lifecycle_normal.py','run_usb_candidate_gates.py','backend_pytest.py','verify_usb_async_visual_boundary.py','capture_usb_async_visual.py','recapture_usb_async_visual.py','inspect_usb_async_visual.py','capture_usb_async_isolated.py','isolated-render-baseline.py','isolated-render-current.py']:
    copy(task/name,'runners/'+name)
for name in ['app/usb_ground_flow.py','ui/main_window.py','ui/pages/build.py','ui/pages/ground_target.py']:
    p=repo/('apps/SCG/src/silverstar_fccg/'+name)
    if p.is_file():copy(p,'owning-source/'+name)
for name in ['test_usb_gui_flow.py','test_usb_gui_async.py','test_usb_lifecycle_normal.py']:
    copy(repo/('apps/SCG/tests/'+name),'owning-source/tests/'+name)
record['daily_head']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','rev-parse','HEAD'],text=True).strip()
record['daily_status']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','status','--porcelain'],text=True).splitlines()
assert record['daily_head']=='56448bd35736221d7885a26704f2f953b0fe5055'
record['retention_scope']='Complete final receipts/source-snapshot/commands, exact saved models/pointers/quality receipts, ELF/map/stack artifacts, selected first-party/derived source, real lifecycle Host fixtures, failed/passed history and real Qt timing. Vendor originals retained at pinned paths with hashes, not duplicated.'
record['files_sha256']={p.relative_to(archive).as_posix():sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
record['listed_bytes']=sum((archive/p).stat().st_size for p in record['files_sha256'])
(archive/'verification.json').write_text(json.dumps(record,indent=2),encoding='utf8',newline='\n')
summary={k:record[k] for k in ['code_commit','normal_tests','builds','refresh_response','build_response','daily_head','daily_status']}
summary.update(listed_files=len(record['files_sha256']),listed_bytes=record['listed_bytes'],manifest_sha256=sha(archive/'verification.json'))
(task/'usb-async-archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps(summary,indent=2))
