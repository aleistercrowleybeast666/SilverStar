from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess,re,shutil
task=Path(__file__).parent
repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
code='838f148059020b05d0de4a735332abf830f8b953'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
archive=repo/'apps/SCG/docs/evidence/native_usb_first_batch_runtime_20261010'
assert not archive.exists()
archive.mkdir(parents=True)
(archive/'.gitattributes').write_bytes(b'* -text\n')
def digest(body):return hashlib.sha256(body).hexdigest()
def copy(source,relative):
    target=archive/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(source).read_bytes())
records={'code_commit':code,'source_scope':'PRIVATE_FIRST_BATCH_F103_C071_RUNTIME',
    'created_utc':datetime.now(timezone.utc).isoformat(),'formal_release':False,
    'independent_usb_safety_review':'NO_PASSED_OUTCOME; earlier platform-stopped review was not retried or bypassed',
    'normal_tests':{},'builds':[],'gates':{},'history':{},
    'retention_scope':'Selected generated/derived sources, tool/command receipts, ELF/maps/stack usage and gate logs. Original vendor inputs and all intermediate .o/.s/.d remain at recorded temporary output paths; no second bulk vendor copy in this archive.'}
for label in ('uc08','ucr03','ucb01'):
    receipt=json.loads((task/(label+'-command.json')).read_text())
    assert receipt['source_commit']==code and receipt['exit']==0,label
    log=(task/(label+'.log')).read_text(encoding='utf8')
    count=int(re.findall(r'(\d+) passed',log)[-1])
    assert not re.search(r'\d+ (?:failed|skipped|error)',log),label
    records['normal_tests'][label]={'passed':count,'skipped':0,'command_receipt':label+'-command.json',
        'scope':receipt['scope'],'source_commit':code}
    for suffix in ('.log','-command.json','-build-index.jsonl'):
        p=task/(label+suffix)
        if p.is_file():copy(p,'runs/'+p.name)
for label in ('ucg02','ucb01'):
    p=task/(label+'-gates.json');gates=json.loads(p.read_text())
    assert gates and all(r['exit']==0 for r in gates),label
    records['gates'][label]=gates
    copy(p,'runs/'+p.name)
    for p in task.glob(label+'-*.log'):copy(p,'runs/'+p.name)
for label in ('uc01','uc02','uc03','uc04','uc05','uc06','uc07','ucr01','ucr02','ucg01'):
    p=task/(label+'.log')
    if p.is_file():
        copy(p,'history/'+p.name)
        record=task/(label+'-command.json')
        if record.is_file():
            copy(record,'history/'+record.name)
            records['history'][label]=json.loads(record.read_text())['exit']
    p=task/(label+'-gates.json')
    if p.is_file():copy(p,'history/'+p.name)
for p in (task/'run_usb_backend_tests.py',task/'run_normal_regression.py',task/'run_backend_tests.py',
        task/'run_usb_candidate_gates.py',task/'backend_pytest.py',Path(__file__)):
    copy(p,'runners/'+p.name)
for label in ('uc08','ucb01'):
    rows=[json.loads(line) for line in (task/(label+'-build-index.jsonl')).read_text().splitlines()]
    for row in rows:
        root=Path(row['output']);family=row['part'];name=label+'/'+family
        receipt=json.loads((root/'receipt.json').read_text());backend=json.loads((root/'backend-receipt.json').read_text())
        assert receipt['source_commit']==code and not receipt['auditable_dirty_diff']
        assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
        assert not receipt['warning_diagnostics'] and all(c['exit']==0 for c in receipt['commands'])
        assert backend['status']=='CompiledCandidate' and not backend['failure']
        assert backend['compile_receipt_sha256']==digest((root/'receipt.json').read_bytes())
        fields={'label':label,'part':family,'output':str(root),'source_commit':code,'commands':len(receipt['commands']),
            'model_sha256':receipt['runtime_model_sha256'],'core':receipt['facts']['core'],
            'toolchain':receipt['toolchain_version'],'irq_header_sha256':receipt['facts']['irq_header_sha256'],
            'irq_enumerators':len(receipt['facts']['irq_numbers']),'independent_irq_slots':receipt['contract']['independent_irq_slots'],
            'elf_sha256':{build:digest((root/build/'native.elf').read_bytes()) for build in ('build','build/analysis')},
            'native_classic_cdc_input':family!='STM32C071FBP6','formal_release':False,
            'object_count_per_build':len(receipt['graph']['sources'])+len(receipt['graph']['asm_sources'])}
        records['builds'].append(fields)
        for p in root.rglob('*'):
            if not p.is_file():continue
            relative=p.relative_to(root).as_posix()
            selected=(relative in {'receipt.json','backend-receipt.json','source-snapshot.json','commands.log','Makefile','candidate_config.ssproject'}
                or relative.startswith(('Generated/','Tools/','HardwareGenerated/ReviewedNativeControl/',
                    'HardwareGenerated/ReviewedC071Hal/','HardwareGenerated/ReviewedC071Radio/','Platform/STM32C0/'))
                or relative in {'build/native-artifact-report.json','build/native.elf','build/analysis/native.elf',
                    'build/native.map','build/analysis/native.map','build/vectors.bin','build/analysis/vectors.bin'}
                or (relative.startswith('build/') and p.suffix=='.su'))
            if selected:copy(p,'final/'+name+'/'+relative)
records['daily_head']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','rev-parse','HEAD'],text=True).strip()
records['daily_status']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','status','--porcelain'],text=True).splitlines()
assert records['daily_head']=='56448bd35736221d7885a26704f2f953b0fe5055'
records['files_sha256']={p.relative_to(archive).as_posix():digest(p.read_bytes()) for p in sorted(archive.rglob('*')) if p.is_file()}
(archive/'verification.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
report='''# First-batch USB private runtime increment — 2026-10-10

Code tested: `'''+code+'''`; base `658cc4c3d4cf6a24b436ab8f4be74a88efed5ee4`. Only `D:\\python_software\\SilverStar\\.work\\ccdi`, branch `feature/scg-classic-cdc-contract-20261009`, was developed. No hardware, serial/DAPLink, flashing/START, GUI/FINAL change, daily merge or push.

Ordinary implementation is complete for the exact private F103C8T6/72 MHz and C071FBP6/48 MHz first-batch recipes. This is a private integration candidate, not a claim of general usable native USB delivery. Formal generation remains blocked. The earlier b66 USB independent safety review was stopped by the platform; it has NO PASSED OUTCOME and was neither retried nor bypassed. EP0/full async lifecycle acceptance, manual critical contracts, whole-program stack/WCET and hardware remain NOT PROVEN.

C071 now uses unified Import → save/reload → Plan/Export → shared Build. Its input is the exact native PCD-only CubeMX project plus the byte-pinned 0.1.1 classic CDC companion from b66f142. Native HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD inputs remain archived unchanged; compiled main/MSP/USB adapters and three narrow HAL derivatives are explicit and hash-bound. Original and derived library sources, licenses and reproducible patches remain present. Rejecting `_sbrk` is retained, the original sysmem is uncompiled, and the USB class uses one static bounded block. The existing single main radio owner repair is reused so SysTick/USB IRQs remain live during radio waiting. Legal GCC M0+ `armv6s-m` and const GPIO read ABI are checked alongside real object/ELF attributes and independent SDK IRQn slots. Phase-1 C071 models must be reimported to binding format 3; project flags do not grant release authority.

F103 ordinary shared control integration composes valid GET/SET line coding and control-line metadata with the existing bulk initialization, cleanup, LL error and session/queue ownership behavior. Original ST sources remain unchanged with original-to-final patches. This integration is not an independent safety review. F407 retains its existing separate private API/candidate/tests; the unified first-batch dispatcher rejects it, and no new F407 adaptation or release was added.

Each run is separate; there is no combined whole-repository PASS:

'''
for label,r in records['normal_tests'].items():report+=f"- `{label}`: {r['passed']} passed, 0 skipped; {r['scope']}\n"
report+='\n'
for b in records['builds']:
    report+=f"- `{b['label']}` / `{b['part']}`: {b['commands']} actual commands all exit 0, {b['object_count_per_build']} objects per build, normal and analyzer ARM links, no compiler/analyzer warnings. ELF normal `{b['elf_sha256']['build']}`; analyzer `{b['elf_sha256']['build/analysis']}`.\n"
report+='\nThe final unified F103/C071 outputs each passed architecture, ordinary generated-source Host, current artifact and unchanged PoT checks (`ucg02`). Existing private F103/F407 outputs each passed their existing four checks (`ucb01-gates`). F407 normal ELF is byte-identical to the earlier `5a9414e97a5e7f3f02d2e001266145304b711c600c16639e05e7e7a79aa44bf8` baseline. C071 Host uses a mocked endpoint service for the established bridge/transport cases; it does not prove its full hardware USB lifecycle. The separate valid F103 Host policy test exercises standard seven-byte GET/SET and DTR/RTS only. No malformed USB/owner-expression tests or blocked review were run. The existing pytest unknown `cache_dir` warning is recorded separately from firmware zero-warning acceptance.\n\n'
report+='Recorded failed/intermediate runs remain in history: uc01 resource binding, uc03 M0+ arch declaration, uc04 const GPIO ABI, uc05 radio source spelling, uc06 two UART analyzer pointer diagnostics, and ucr01 missing fixture import. These were repaired and rerun; none is represented as a passed final build. uc02, uc07, ucr02 and ucg01 are intermediate scoped passes, not evidence for the final commit.\n\n'
report+='Evidence: `evidence/native_usb_first_batch_runtime_20261010/verification.json`. Its manifest enumerates exactly the retained subset; full native inputs and intermediate objects remain at the receipt paths. The archive includes both ELF/map sets, generated/derived sources, stack-usage files, command logs, source snapshots and gate logs without another bulk vendor copy. Daily HEAD remains `'+records['daily_head']+'`, with the same three existing inventory files untracked. Parent ordinary review and any later user-notified local acceptance merge are separate; no formal USB release is authorized by these results.\n'
path=repo/'apps/SCG/docs/NATIVE_USB_FIRST_BATCH_RUNTIME_20261010.md'
path.write_text(report,encoding='utf8',newline='\n')
(task/path.name).write_text(report,encoding='utf8',newline='\n')
for filename in ('NATIVE_CLASSIC_CDC_RUNTIME_20261010.md','NATIVE_CLASSIC_CDC_TIMER_20261010.md'):
    p=repo/'apps/SCG/docs'/filename
    with p.open('a',encoding='utf8',newline='\n') as stream:
        stream.write('\n\nVersion note: this report retains its original snapshot scope. The later exact F103/C071 private runtime increment and shared F103 ordinary control integration are recorded in [NATIVE_USB_FIRST_BATCH_RUNTIME_20261010.md](NATIVE_USB_FIRST_BATCH_RUNTIME_20261010.md), tested code `'+code+'`. Independent USB safety review still has NO PASSED OUTCOME; formal generation remains blocked.\n')
print(json.dumps({'code_commit':code,'archive':str(archive),'manifest_sha256':digest((archive/'verification.json').read_bytes()),
    'listed_files':len(records['files_sha256']),'report':str(path),'report_sha256':digest(path.read_bytes()),'builds':records['builds']},indent=2))
