"""Preserve the distinct F407 timer probe scope, all attempts and frozen inputs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,subprocess

ROOT=Path('D:/python_software/SilverStar');REPO=ROOT/'.work/ccdi'
TEMP=Path('C:/Users/chdxm/AppData/Local/Temp')
FINAL=TEMP/'sscdc-timer-f407-13d'
OUT=REPO/'apps/SCG/docs/evidence/native_classic_cdc_timer_20261010'
BASE='179467265ec32ba79f7fb4bef85a4dfad82f8618'

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
receipt=json.loads((FINAL/'receipt.json').read_text());snapshot=json.loads((FINAL/'source-snapshot.json').read_text())
assert receipt['source_commit']==snapshot['source_commit']==BASE
assert receipt['validation_scope']=='PRIVATE_NATIVE_TIM1_CLOCK_HAL_USB_CONFIG_PROBE'
assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
assert receipt['failure'] is None and not receipt['warning_diagnostics']
assert receipt['commands'] and all(c['exit']==0 for c in receipt['commands'])
for key in ('experimental_files_sha256','output_artifact_sha256'):
    for path,digest in receipt[key].items():assert sha(FINAL/path)==digest,path
for path,record in snapshot['modules'].items():assert sha(REPO/'apps/SCG'/path)==record['sha256'],path
for name in ('p10','architecture','artifact'):
    stem='ccdi-'+name+'-timer13d'
    assert (ROOT/'.work'/(stem+'.exit')).read_text().strip()=='0',stem
    if name=='p10':
        text=(ROOT/'.work'/(stem+'.log')).read_text(encoding='utf-8-sig')
        assert 'POWER10_CONTRACT_REVIEW|NOT_PROVEN' in text and 'project text checks passed' in text
test_log=(ROOT/'.work/ccdi-native-final13d.log').read_text(encoding='utf-8-sig')
assert (ROOT/'.work/ccdi-native-final13d.exit').read_text().strip()=='0'
count=re.search(r'(\d+) passed(?:, 1 warning)? in ([\d.]+)s',test_log)
assert count and int(count[1])==187 and ' failed' not in test_log and ' skipped' not in test_log
assert (ROOT/'.work/ccdi-host-timer13d.exit').read_text().strip()=='1'
assert 'NOT PROVEN: timer probe has no Ground host program' in (ROOT/'.work/ccdi-host-timer13d.log').read_text(encoding='utf-8-sig')
assert sha(FINAL/'Tools/check_power_of_ten.ps1')==sha(REPO/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1')
assert not OUT.exists();OUT.mkdir(parents=True);(OUT/'.gitattributes').write_text('* -text\n')
manifest={}
def copy(path,target):
    dest=OUT/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    manifest[target]={'origin':str(path),'sha256':sha(dest),'bytes':dest.stat().st_size}

copy(Path(__file__),'runners/'+Path(__file__).name)
for name in ('ccdi_run.py','ccdi_prepare_f40713.py','ccdi_timer_host13.py'):
    copy(ROOT/'.work'/name,'runners/'+name)
for name in ('normal_test_paths','closeout_test_paths'):
    copy(ROOT/('docs/evidence/nightly_software_20261008/'+name+'.py'),'runners/'+name+'.py')
copy(ROOT/'.work/ccdi_facts/f407-usb13.json','configuration/f407-usb13-facts.json')
copy(ROOT/'.work/ccdi-timer-host-fault13d.json','host-fault-evidence/final-execution.json')
for suffix in ('log','exit'):
    copy(ROOT/'.work'/('ccdi-timer-host-fault13d.'+suffix),'host-fault-evidence/final-execution.'+suffix)
for path in snapshot['modules']:copy(REPO/'apps/SCG'/path,'source_snapshot/apps/SCG/'+path)
patterns=('ccdi-tim13*.*','ccdi-tim-config13*.*','ccdi-usb-config13*.*','ccdi-timer-f407-13*.*',
    'ccdi-native-final13*.*','ccdi-p10-timer13*.*','ccdi-architecture-timer13*.*','ccdi-artifact-timer13*.*',
    'ccdi-host-timer13*.*')
for path in sorted({p for pattern in patterns for p in (ROOT/'.work').glob(pattern)}):
    if path.is_file():copy(path,'attempts/'+path.name)
history=[]
for attempt in ('13a','13b','13c','13d'):
    directory=TEMP/('sscdc-timer-f407-'+attempt)
    for name in ('source-snapshot.json','receipt.json','commands.log'):
        if (directory/name).is_file():copy(directory/name,'builds/'+attempt+'/'+name)
    if (directory/'receipt.json').is_file():
        old=json.loads((directory/'receipt.json').read_text())
        history.append({'directory':str(directory),'status':old['status'],'failure':old.get('failure'),
            'warning_count':len(old['warning_diagnostics']),'commands':len(old['commands']),
            'acceptance':'13c Power10 FAILED; final 13d is a separate scope/snapshot' if attempt=='13c' else 'Recorded scope only'})
    else:history.append({'directory':str(directory),'status':'FAILED BEFORE RECEIPT','acceptance':'Partial output, not accepted'})
for name in ('build/native-artifact-report.json','Generated/native_probe_contract.json',
    'Generated/ground_source_graph.json','Makefile'):
    copy(FINAL/name,'final/'+name)
for build in ('build','build/analysis'):
    for name in ('native.elf','native.map','vectors.bin','native-artifact-vectors.bin'):
        copy(FINAL/build/name,'final/'+build+'/'+name)
for path in (FINAL/'build').rglob('*.su'):
    copy(path,'final/'+path.relative_to(FINAL).as_posix())
for path in receipt['experimental_files_sha256']:
    if path.endswith(('.c','.h','.patch','.py','.ps1','.ld')):
        copy(FINAL/path,'final/'+path)
host_artifacts={}
for attempt in ('sscdc-tim13a','sscdc-tim13b','sscdc-tim-config13c','sscdc-tim-config13e','sscdc-native-final13c','sscdc-native-final13d'):
    directory=TEMP/attempt
    if not directory.is_dir():continue
    for path in directory.rglob('*'):
        if path.is_file() and (path.name in ('original.c','derived.c','timer-port.c') or path.name.endswith('-command.json') or
                (path.suffix=='.log' and path.name.startswith(('original-','derived-','timer-')))):
            target='host-fault-evidence/'+attempt+'/'+path.relative_to(directory).as_posix()
            copy(path,target);host_artifacts[target]={'sha256':sha(path),'bytes':path.stat().st_size}
versions={}
for name,command in [('python',[str(ROOT/'apps/FLP/.venv/Scripts/python.exe'),'--version']),
    ('host_gcc',['gcc','--version']),('arm_gcc',['arm-none-eabi-gcc','--version']),('git',['git','--version']),
    ('power10_shell',['powershell','-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()'])]:
    result=subprocess.run(command,capture_output=True,text=True,timeout=30);assert result.returncode==0
    versions[name]={'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
verification={'created_utc':datetime.now(timezone.utc).isoformat(),'source_baseline':BASE,
    'tested_source':'Auditable dirty source snapshot and exact-byte source archive; documentation/evidence copied afterward',
    'scope':'Private actual F407 TIM1 clock, recognized HAL derivatives, explicit native USB configuration and no-heap ARM probe; NOT Ground runtime',
    'compile_commands':len(receipt['commands']),'compiler_warnings':0,
    'experimental_file_hashes':len(receipt['experimental_files_sha256']),'artifact_hashes':len(receipt['output_artifact_sha256']),
    'final_output':str(FINAL),'native_tests':{'passes':int(count[1]),'seconds':float(count[2]),'skips':0,
        'existing_config_warning':'Unknown config option: cache_dir' in test_log},
    'commands':{'compile':['python','-B','apps/SCG/tools/validation/native_classic_cdc_compile.py','--input',
        'C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation/cube-f407-usb','--device-facts',
        str(ROOT/'.work/ccdi_facts/f407-usb13.json'),'--output',str(FINAL),'--spi','SPI1','--gpio','RADIO_NSS','RADIO_RST','RADIO_BUSY','RADIO_DIO1',
        '--clock-hz','168000000','--native-timer-probe'],
        'power10':['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','Tools/check_power_of_ten.ps1','-TargetKind','Ground'],
        'architecture':['python','-B','Tools/check_native_probe.py','architecture'],
        'artifact':['python','-B','Tools/check_native_probe.py','artifact'],
        'host_fault_fixture_runs':['python','-B',str(ROOT/'.work/ccdi_timer_host13.py')],
        'native_tests':['python','-B',str(ROOT/'.work/ccdi_run.py'),*[str(p) for p in sorted((REPO/'apps/SCG/tests').glob('test_native*.py'))],
            '--basetemp='+str(TEMP/'sscdc-native-final13d'),'-q']},
    'environment':{'python':str(ROOT/'apps/FLP/.venv/Scripts/python.exe'),'host_bin':'D:/msys64/ucrt64/bin',
        'arm_bin':'D:/Arm GNU Toolchain/14.3 rel1/bin','PYTHONDONTWRITEBYTECODE':'1','QT_QPA_PLATFORM':'offscreen',
        'SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT':'C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation'},
    'versions':versions,'history':history,'host_artifacts':host_artifacts,
    'normal_generation':'BLOCKED','f103_runtime_checkpoint':BASE,'f407_ground_runtime':'NOT IMPLEMENTED OR ACCEPTED',
    'critical_contract_review':'NOT PROVEN','ep0':'b66 independent review interrupted by platform safety; no outcome; not retried/integrated',
    'manual_review':{'performed':'Ordinary local source/ownership/fault-path review; not independent EP0 review or acceptance',
        'confirmed':['Native inputs immutable; only owned derivative paths compiled',
            'Actual TIM1 IRQ dispatch restored; APB2 DIV1 uses PCLK2, other admitted divider uses twice PCLK2',
            'Invalid initial priority rejects before hardware configuration; initial failures retain ordinary HAL errors',
            'Pending UIF snapshots reject instead of inventing HAL ticks; three retries restore PRIMASK',
            'Main context and verified actual timer setup required before sample publication',
            'Fixed timer callback compile contract and reviewed device header require no new preprocessing exceptions',
            'Actual normal/analyzer CPP dependencies select the reviewed config and timer headers',
            'Probe graph has one rejecting heap owner and actual linked strong timer/init/callback objects'],
        'unresolved':['Reinitialization IRQ/config sequence, missed update counts/IRQ latency and all timer callers remain NOT PROVEN',
            'C source recognizers do not prove complete call-graph ownership or semantic checked-return coverage',
            'F407 distinct indexed class/LL/data lifecycle and EP0 remain unaccepted',
            'HAL/fixed USB callbacks and static USB allocation remain controlled vendor exceptions',
            'First-party Power10 PASS excludes native/derived vendor sources and does not certify whole firmware',
            'Library/indirect-call stack, MSP/ISR nesting, WCET and physical hardware remain NOT PROVEN']},
    'daily_unchanged':{'head':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),
        'gui_hash_count':len(frozen),'original_untracked_hashes':original},'files':manifest}
(OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT),'files':len(manifest),'commands':len(receipt['commands']),
    'artifacts':len(receipt['output_artifact_sha256']),'tests':verification['native_tests']},indent=2))
