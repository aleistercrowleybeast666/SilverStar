from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
task=Path(__file__).parent
repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
code='80db26338bba77950a9b8e9bbc03d8a77e33567b'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
archive=repo/'apps/SCG/docs/evidence/native_usb_lifecycle_normal_20261010'
assert not archive.exists()
archive.mkdir(parents=True)
(archive/'.gitattributes').write_bytes(b'* -text\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(p,relative):
 dest=archive/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(Path(p).read_bytes())
records={'code_commit':code,'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'PRIVATE_FIRST_BATCH_ORDINARY_USB_LIFECYCLE','formal_release':False,'independent_usb_safety_review':'NO_PASSED_OUTCOME; platform-stopped b66 review not retried or bypassed','normal_tests':{},'builds':[],'gates':{},'history':{}}
for label in ('ul14','uc09','ucr04'):
 receipt=json.loads((task/(label+'-command.json')).read_text(encoding='utf8'))
 assert receipt['source_commit']==code and receipt['exit']==0,label
 log=(task/(label+'.log')).read_text(encoding='utf8')
 assert not re.search(r'\d+ (?:failed|error|skipped)',log),label
 records['normal_tests'][label]={'passed':int(re.findall(r'(\d+) passed',log)[-1]),'skipped':0,'scope':receipt['scope'],'source_commit':code}
 for suffix in ('.log','-command.json','-build-index.jsonl'):
  p=task/(label+suffix)
  if p.is_file():copy(p,'runs/'+p.name)
for p in sorted(Path(r'C:\Users\chdxm\AppData\Local\Temp\ul14').glob('test_normal*/lifecycle-receipt.json')):
 d=json.loads(p.read_text());assert len(d['runs'])==12 and all(r['exit']==0 for r in d['runs'])
 records.setdefault('lifecycle_runs',[]).append(d)
 for f in p.parent.iterdir():
  if f.is_file():copy(f,'host/'+d['part']+'/'+f.name)
for label in ('ul01','ul02','ul03','ul04','ul05','ul06','ul07','ul08','ul09','ul10','ul11','ul12','ul13'):
 receipt=json.loads((task/(label+'-command.json')).read_text())
 records['history'][label]={'exit':receipt['exit'],'source_commit':receipt['source_commit'],'test_sha256':receipt['test_sha256']}
 copy(task/(label+'-command.json'),'history/'+label+'-command.json');copy(task/(label+'.log'),'history/'+label+'.log')
 if label in ('ul07','ul09','ul10'):
  for p in Path('C:/Users/chdxm/AppData/Local/Temp/'+label).glob('test_normal*/lifecycle-receipt.json'):
   part=json.loads(p.read_text())['part']
   for f in p.parent.iterdir():
    if f.is_file():copy(f,'history/'+label+'/'+part+'/'+f.name)
gates=json.loads((task/'ucg03-gates.json').read_text());assert len(gates)==8 and all(g['exit']==0 for g in gates)
records['gates']['ucg03']=gates
copy(task/'ucg03-gates.json','runs/ucg03-gates.json')
for p in task.glob('ucg03-*.log'):copy(p,'runs/'+p.name)
rows=[json.loads(line) for line in (task/'uc09-build-index.jsonl').read_text().splitlines()]
for row in rows:
 root=Path(row['output']);backend=json.loads((root/'backend-receipt.json').read_text());receipt=json.loads((root/'receipt.json').read_text())
 assert receipt['source_commit']==code and receipt['auditable_dirty_diff']=='' and not receipt['warning_diagnostics']
 assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED' and all(c['exit']==0 for c in receipt['commands'])
 assert backend['model_sha256']==receipt['runtime_model_sha256'] and backend['compile_receipt_sha256']==sha(root/'receipt.json')
 project=Path(row.get('project_root',row.get('project')))
 runtime=project/'SilverStar.ssproject'
 assert sha(runtime)==sha(root/'candidate_config.ssproject')
 assert receipt['runtime_project']==str(runtime.resolve()) and receipt['runtime_project_sha256']==sha(runtime)
 if row['part']=='STM32C071FBP6':
  assert row['backend_receipt_sha256']==sha(root/'backend-receipt.json')
  assert row['compile_receipt_sha256']==sha(root/'receipt.json')
  assert backend['project_root']==str(project.resolve()) and backend['runtime_project']==str(runtime.resolve())
  assert Path(backend['snapshot_root']).is_dir() and backend['snapshot_root']==receipt['snapshot_root']
 fact={'part':row['part'],'output':str(root),'project_root':str(project),'runtime_project':str(runtime),'runtime_project_sha256':sha(runtime),'snapshot_root':receipt['snapshot_root'],'model_sha256':receipt['runtime_model_sha256'],'backend_receipt_sha256':sha(root/'backend-receipt.json'),'compile_receipt_sha256':sha(root/'receipt.json'),'commands':len(receipt['commands']),'toolchain_version':receipt['toolchain_version'],'irq_header_sha256':receipt['facts']['irq_header_sha256'],'elf_sha256':{p:sha(root/p) for p in ('build/native.elf','build/analysis/native.elf')}}
 records['builds'].append(fact)
 copy(runtime,'final/'+row['part']+'/saved_project/SilverStar.ssproject')
 for f in root.rglob('*'):
  if not f.is_file():continue
  relative=f.relative_to(root).as_posix()
  keep=(relative.startswith(('Generated/','Platform/STM32C0/','HardwareGenerated/ReviewedC071Lifecycle/','HardwareGenerated/ReviewedNativeControl/','Tools/')) or relative in ('Makefile','receipt.json','backend-receipt.json','backend-owner.json','candidate_config.ssproject','commands.log') or (relative.startswith('build/') and (f.suffix in ('.elf','.map','.su') or f.name in ('source_snapshot.json','commands.log'))))
  if keep:copy(f,'final/'+row['part']+'/'+relative)
for p in (task/'run_lifecycle_normal.py',task/'backend_pytest.py',task/'run_usb_backend_tests.py',task/'run_normal_regression.py',task/'run_usb_candidate_gates.py',Path(__file__)):
 copy(p,'runners/'+p.name)
records['host_toolchain']=subprocess.check_output([r'D:\msys64\ucrt64\bin\gcc.exe','--version'],text=True).splitlines()[0]
records['daily_head']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','rev-parse','HEAD'],text=True).strip()
records['daily_status']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','status','--porcelain'],text=True).splitlines()
assert records['daily_head']=='56448bd35736221d7885a26704f2f953b0fe5055'
records['retention_scope']='Selected generated USB/adapter sources, actual Host fixtures/executables, failed and passed logs, saved exact model, compiler/backend receipts, both normal/analyzer ELF/maps/stack usage. Native/vendor originals remain pinned in earlier archives and receipt snapshot paths; all intermediate objects remain in the original build outputs.'
records['files_sha256']={p.relative_to(archive).as_posix():sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
(archive/'verification.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')
report=f'''# First-batch ordinary USB lifecycle closure - 2026-10-10

Tested code `{code}`; prior code/evidence `838f148` / `e176458`. Worktree `D:\\python_software\\SilverStar\\.work\\ccdi`, branch `feature/scg-classic-cdc-contract-20261009`. The earlier parent ordinary review covered 838/e176 only, not this increment. The platform-stopped independent b66 USB safety review still has NO PASSED OUTCOME; it was not retried or bypassed. No malformed USB input or alternate-owner expression research was performed. Formal generation remains blocked.

## Concrete ordinary lifecycle coverage

| Operation | F103C8T6 / 72 MHz | C071FBP6 / 48 MHz |
|---|---|---|
| Normal enumeration | Actual generated core/ctlreq/ioreq/class/descriptor sources: device descriptor, 9-byte configuration header then complete multi-packet configuration, language/manufacturer/product/serial strings, valid address/configuration and both interfaces queried | Same; native PCD plus byte-pinned companion remains the exact input classification |
| Valid class control | Seven-byte SET/GET line coding plus DTR/RTS through the real generated call sites | Same through the real C071 interface implementation |
| RX and TX lifetime | 64-byte RX is copied into the bounded stream; caller TX bytes are copied and cannot overwrite pending transfer; 64-byte TX remains owned through a trailing ZLP | Same; existing transmit completion callback and endpoint service are present |
| Unconfigure/reset/disconnect/reconnect | Actual core/class retirement clears unread RX and old sessions, cancels pending TX and pending valid control OUT; fresh configuration accepts only the new session | Same |
| Stop and DeInit | Success closes all endpoints before class free; DeInit errors propagate and allow cleanup retry | Same; repaired class/core derivatives retained with provenance |
| Failed endpoint close | Class and TX bytes retained, write blocked, retry frees only after successful close | Repaired; pre-fix class free happened despite CloseEP failure |
| Reinit after failed cleanup | Rejected while class resources remain, preserving the cleanup binding | Repaired; pre-fix Init could overwrite the retained class binding |
| Initial endpoint open / RX arm failure | Existing failure abort/cleanup checked with valid SET_CONFIGURATION | Repaired; pre-fix native class discarded both LL results and published configured state |
| TX start returns failure | Session invalidated; ambiguous TX bytes remain owned until successful retirement | Existing LL-result hook/endpoint service invalidates the session; TxState and bytes remain owned until retirement |
| RX rearm returns failure | Existing failure path deconfigures and discards old-session unread bytes | Existing endpoint service retries the arm on the main owner; accepted bytes remain readable once in their session |

The final Host run contains two target tests executing twelve named scenarios each (24 scenario executions), not 24 independent pytest tests. HAL/PCD controller calls, UID registers, static allocator accounting and Cortex intrinsics are explicit Host substitutes. These tests establish the recorded normal core/class/adapter sequence and buffer contracts. They do not execute native HAL/PMA/IRQ internals or prove every IRQ/main interleaving, suspend/resume corner, actual host-driver behavior, or physical transfer cancellation. Hardware is unnecessary for the software checks completed here; these remaining limits are not being used to excuse a known normal implementation defect. Whole-program stack/WCET and manual critical-contract acceptance remain separate NOT PROVEN items.

## Repairs and traceability

C071 compiles two explicit additional ordinary lifecycle derivatives of the pinned b66 class/core, without changing the original companion or its EP0 functions. Narrow init/deinit/stop changes check real LL returns, retain class memory on failed endpoint closure, propagate errors, and reject reinitialization until cleanup succeeds. Original-to-derived hashes and reproducible patches are verified by the architecture gate. C071 private Export now emits a Makefile matching the final source graph and rejecting heap owner; shared compilation still emits its additional ABI probe truthfully. F103 composes its top-level Init/DeInit guard/result repair with the existing ordinary control/bulk derivative. F407 adaptation and GUI source remain unchanged.

Parent P3 is repaired: C071 backend receipt and build index now save project_root, runtime_project, snapshot_root and receipt hashes. The shared compiler also saves runtime_project, its byte hash and snapshot_root. Fresh tests assert these paths and hashes, and this archive retains the saved model itself.

## GUI entry wiring still required

It is not only a release gate. Existing widgets can remain visually unchanged, but their handlers are wired to the older ordinary flow:

1. `ui/main_window.py:_GroundCubeMxImport_Request` calls `CubeMxProject_Import`, not `UsbGroundProject_Import`. An exact-target dispatcher must resolve trusted SDK/companion facts and the fixed clock/SPI/GPIO recipe. Unknown configurations must continue to reject.
2. `_GroundCubeMxImport_Complete` currently reconstructs hardware and clears resource assignments. It must apply the returned bound model without discarding binding/resources, then use the existing save/reload flow. The F103 private model and C071 PCD-only capability representation must remain truthful.
3. `_GenerateOrApply_Request` uses `GenerationPlan_Create/Apply`, whose formal guard intentionally rejects these candidates. Integration needs an explicit candidate Plan/Export result adapter and safe disjoint output handling; it cannot simply remove the guard or mark a candidate formally ready.
4. `_TargetAction_Request` uses `BuildRunner.Target_Run` on an existing Ground_Station Makefile and assumes `build/ground.elf` plus a catalog MCU ID. The new route must dispatch `UsbGroundCandidate_Build`, preserve its compiler/backend/model receipts and use its actual `build/native.elf`/analyzer artifacts and independent device facts. Cancellation/progress and artifact display need corresponding result handling. The private Build API currently has no GUI cancellation/progress callback contract; that wiring remains to be implemented before a usable normal GUI path is claimed.
5. Quality/result status must display the completed software checks and outstanding acceptance separately; formal release still needs its applicable acceptance decision. No GUI behavior or styling was changed in this increment.

## Separate final verification runs

'''
for label,r in records['normal_tests'].items():report+=f"- `{label}`: {r['passed']} passed, 0 skipped, exact source `{code}`.\n"
for b in records['builds']:report+=f"- `{b['part']}`: {b['commands']} actual commands all exit 0; normal/analyzer ARM links, no compiler/analyzer diagnostics. ELF normal `{b['elf_sha256']['build/native.elf']}`; analyzer `{b['elf_sha256']['build/analysis/native.elf']}`.\n"
report+='\n`ucg03` contains eight successful checks: architecture, ordinary generated Host, current artifact and unchanged PoT for each exact target. The generated bridge Host gate still uses its established C071 endpoint-service mock; the separate lifecycle run above compiles the actual C071 interface and service. Existing pytest unknown cache_dir warnings and Host vendor unused-parameter warnings are retained and are separate from firmware zero-warning acceptance. No whole-repository or independent safety PASS is claimed.\n\n'
report+='Pre-fix evidence is retained: ul07 C071 premature class free; ul09 F103 DeInit failure loss and C071 retained-class reinit; ul10 C071 initial OpenEP/RX-arm failure loss. ul01-06 also retain Host-fixture declaration/model errors (including ST normal EP0 status-phase stalls), which were corrected without weakening the data, return, lifetime or session expectations. ul08/11/12/13 are intermediate scoped passes; ul14 is the final exact-commit run.\n\n'
report+='Evidence: `evidence/native_usb_lifecycle_normal_20261010/verification.json`. Its manifest enumerates the retained subset and build/saved-model/receipt paths. Daily HEAD remains `56448bd35736221d7885a26704f2f953b0fe5055` with the same three untracked inventory files. No hardware, serial/DAPLink, flash/START, GUI/FINAL edit, push or merge occurred. Ordinary lifecycle tests were not platform-rejected; the earlier independent safety review remains blocked. Parent QA for this new commit and any later notified local acceptance merge remain separate.\n'
path=repo/'apps/SCG/docs/NATIVE_USB_LIFECYCLE_NORMAL_20261010.md'
path.write_text(report,encoding='utf8',newline='\n');(task/path.name).write_text(report,encoding='utf8',newline='\n')
print(json.dumps({'code':code,'manifest_sha256':sha(archive/'verification.json'),'listed_files':len(records['files_sha256']),'report':str(path),'report_sha256':sha(path),'builds':records['builds']},indent=2))
