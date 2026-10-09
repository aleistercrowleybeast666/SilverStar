"""Collect the isolated runtime increment without rewriting old evidence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, re

ROOT=Path('D:/python_software/SilverStar')
REPO=ROOT/'.work/ccdi'
TEMP=Path('C:/Users/chdxm/AppData/Local/Temp')
FINAL=TEMP/'sscdc-ground-f103-12c'
OUT=REPO/'apps/SCG/docs/evidence/native_classic_cdc_runtime_20261010'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args,repo=ROOT):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

assert git('rev-parse','HEAD')=='56448bd35736221d7885a26704f2f953b0fe5055'
assert git('branch','--show-current')=='fix/nightly-user-ready-20261003'
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
original=json.loads((ROOT/'.work/scg_ground_integration_20261009/original-files.json').read_text())
assert set(git('ls-files','--others','--exclude-standard').splitlines())=={Path(e['Path']).name for e in original}
for entry in original:assert sha(Path(entry['Path'])).upper()==entry['Hash']
frozen=json.loads((ROOT/'.work/scg_ground_integration_20261009/source-parity.json').read_text())['gui_frozen_sha256']
for path,digest in frozen.items():assert sha(ROOT/path)==digest,path
receipt=json.loads((FINAL/'receipt.json').read_text())
snapshot=json.loads((FINAL/'source-snapshot.json').read_text())
assert receipt['source_commit']==snapshot['source_commit']=='7c6ae5653c4b9696d9da80a20df5297a92b2deb0'
assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
assert receipt['failure'] is None and not receipt['warning_diagnostics']
assert receipt['commands'] and all(c['exit']==0 for c in receipt['commands'])
for key in ('experimental_files_sha256','output_artifact_sha256'):
    for path,digest in receipt[key].items():assert sha(FINAL/path)==digest,path
for path,record in snapshot['modules'].items():assert sha(REPO/'apps/SCG'/path)==record['sha256'],path
for name in ('p10','architecture','host','artifact'):
    stem='ccdi-'+name+'-12c'
    assert (ROOT/'.work'/(stem+'.exit')).read_text().strip()=='0',stem
    if name=='p10':
        text=(ROOT/'.work'/(stem+'.log')).read_text(encoding='utf-8-sig')
        assert 'POWER10_CONTRACT_REVIEW|NOT_PROVEN' in text and 'project text checks passed' in text
test_records={}
for name in ('final-tests','legacy-runtime'):
    stem='ccdi-'+name+'12c'
    assert (ROOT/'.work'/(stem+'.exit')).read_text().strip()=='0',stem
    text=(ROOT/'.work'/(stem+'.log')).read_text(encoding='utf-8-sig')
    count=re.search(r'(\d+) passed(?:, 1 warning)? in ([\d.]+)s',text)
    assert count and ' failed' not in text and ' skipped' not in text,stem
    test_records[name]={'count':int(count[1]),'seconds':float(count[2]),'config_warning':'Unknown config option: cache_dir' in text,'skips':0}
assert not OUT.exists()
OUT.mkdir(parents=True)
(OUT/'.gitattributes').write_text('* -text\n')
manifest={}
def copy(path,target):
    dest=OUT/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    manifest[target]={'origin':str(path),'sha256':sha(dest),'bytes':dest.stat().st_size}

copy(Path(__file__),'runners/'+Path(__file__).name)
for name in ('ccdi_run.py','ccdi_pre_runtime12.py','ccdi_link_inventory_pre12.py'):
    copy(ROOT/'.work'/name,'runners/'+name)
for name in ('normal_test_paths','closeout_test_paths'):
    copy(ROOT/('docs/evidence/nightly_software_20261008/'+name+'.py'),'runners/'+name+'.py')
copy(ROOT/'.work/ccdi-native-ground-config10a.ssproject','configuration/native-ground.ssproject')
for part in ('f103','f407'):
    copy(ROOT/'.work/ccdi_facts'/(part+'-usb.json'),'configuration/'+part+'-facts.json')
for path in snapshot['modules']:
    copy(REPO/'apps/SCG'/path,'source_snapshot/apps/SCG/'+path)
# Complete prior failure/output logs are retained, never merged into a suite pass.
patterns=('ccdi-clock*10*.log','ccdi-clock*10*.exit','ccdi-hal*10*.log','ccdi-hal*10*.exit',
    'ccdi-platform10*.log','ccdi-platform10*.exit','ccdi-runtime*.log','ccdi-runtime*.exit',
    'ccdi-ground-f103-*.log','ccdi-ground-f103-*.exit','ccdi-bulk-*.log','ccdi-bulk-*.exit',
    'ccdi-ll-*.log','ccdi-ll-*.exit','ccdi-radio-*.log','ccdi-radio-*.exit',
    'ccdi-wakeup-*.log','ccdi-wakeup-*.exit','ccdi-pc-*.log','ccdi-pc-*.exit',
    'ccdi-publication-*.log','ccdi-publication-*.exit','ccdi-init-*.log','ccdi-init-*.exit',
    'ccdi-derivative12a.*','ccdi-final-tests12*.*','ccdi-legacy-runtime12*.*','ccdi-linked-inventory*.log','ccdi-linked-inventory*.exit',
    'ccdi-p10-*.log','ccdi-p10-*.exit','ccdi-architecture-*.log','ccdi-architecture-*.exit',
    'ccdi-host-*.log','ccdi-host-*.exit','ccdi-artifact-*.log','ccdi-artifact-*.exit',
    'ccdi-assert-object12b.*','ccdi-noheap-linked12b.*')
for path in sorted({p for pattern in patterns for p in (ROOT/'.work').glob(pattern)}):
    if path.is_file():copy(path,'attempts/'+path.name)
history=[]
for part,kind,attempt in [('f103','ground',n) for n in ('10a','10b','10c','11a','11b','12a','12b','12c')]+[
        ('f407','halclock',n) for n in ('10a','10b')]:
    build=TEMP/('sscdc-'+kind+'-'+part+'-'+attempt)
    if not build.is_dir():continue
    for name in ('source-snapshot.json','receipt.json','commands.log'):
        if (build/name).is_file():copy(build/name,'builds/'+part+'-'+kind+'-'+attempt+'/'+name)
    if (build/'receipt.json').is_file():
        item=json.loads((build/'receipt.json').read_text())
        history.append({'directory':str(build),'status':item['status'],'failure':item.get('failure'),
            'warning_count':len(item['warning_diagnostics']),'commands':len(item['commands']),
            'artifact_count':len(item['output_artifact_sha256']),'acceptance':'Historical scope only; no current pass inferred'})
    else:history.append({'directory':str(build),'status':'FAILED BEFORE RECEIPT','acceptance':'Partial output, not accepted'})
for name in ('build/native-artifact-report.json','build/native-host/ready_transport_fixture.c'):
    copy(FINAL/name,'final/'+name)
for name in ('Generated/native_ground_contract.json','Generated/ground_source_graph.json','Makefile'):
    copy(FINAL/name,'final/'+name)
host_artifacts={}
for directory in ('sscdc-final-tests12c','sscdc-legacy-runtime12c'):
    for path in (TEMP/directory).rglob('*'):
        if path.is_file():host_artifacts[str(path)]={'sha256':sha(path),'bytes':path.stat().st_size}
versions={}
for name,command in [('python',[str(ROOT/'apps/FLP/.venv/Scripts/python.exe'),'--version']),
    ('host_gcc',['gcc','--version']),('arm_gcc',['arm-none-eabi-gcc','--version']),('git',['git','--version']),
    ('power10_shell',['powershell','-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()'])]:
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert result.returncode==0
    versions[name]={'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
verification={'created_utc':datetime.now(timezone.utc).isoformat(),'source_baseline':receipt['source_commit'],
    'tested_source':'Full source-snapshot plus exact-byte source archive; this evidence/doc addition is later, not compiled firmware',
    'scope':'Private F103 source-profile Ground single FS CDC and one M12 SX1281 bare-metal runtime candidate',
    'final_output':str(FINAL),'compile_commands':len(receipt['commands']),'compiler_warning_count':0,
    'experimental_file_hashes':len(receipt['experimental_files_sha256']),'artifact_hashes':len(receipt['output_artifact_sha256']),
    'tests':test_records,'versions':versions,'history':history,'host_artifacts':host_artifacts,
    'daily_unchanged':{'head':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),
        'gui_hash_count':len(frozen),'original_untracked_hashes':original},
    'critical_contract_review':'NOT PROVEN','ep0_review':'b66 independent review interrupted by platform safety; no outcome; not retried/integrated',
    'normal_generation':'BLOCKED','f407_runtime':'NOT PROVEN: actual TIM1 timebase unsupported and distinct class/config profile unresolved; no SysTick substitution or Wundef suppression',
    'limits':['No whole-firmware Power-of-Ten original compliance claim','Vendor fixed callbacks/static allocator controlled exceptions retained',
        'Host HAL/MMIO/radio mocks and test-only terminal trap interception do not establish MCU recovery',
        'Actual task/library/indirect call/MSP/ISR nesting stack, STM32 WCET, clock/radio waveforms and hardware remain NOT PROVEN',
        'Legacy historical sd_sdio_fatfs_f1 missing fixture failure preserved; not a full monorepo suite pass',
        'Old 10c graph/Makefile receipt mismatch and 11b Power10 61-line failure remain historical failures',
        'Existing Power10 text scope excludes native/derived vendor entry/class/LL files; controlled exception and derivative critical contracts require explicit manual review'],
    'files':manifest}
(OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT),'files':len(manifest),'commands':len(receipt['commands']),
    'artifact_hashes':len(receipt['output_artifact_sha256']),'tests':test_records},indent=2))
