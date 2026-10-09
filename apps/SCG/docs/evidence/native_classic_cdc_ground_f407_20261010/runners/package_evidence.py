from pathlib import Path
import hashlib,json,subprocess,shutil,datetime,re,os,sys
root=Path('D:/python_software/SilverStar/.work/ccdi');work=Path(__file__).resolve().parent
stage=work/'evidence-package';assert not stage.exists();stage.mkdir()
code=json.loads((work/'code-checkpoint.json').read_text())['code_commit']
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==code
def sha(data):return hashlib.sha256(data).hexdigest()
def copy(source,relative):
    target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
def checked(root_dir,path,digest):
    actual=(root_dir/path).resolve();assert actual.is_relative_to(root_dir.resolve())
    data=actual.read_bytes();assert sha(data)==digest,(path,sha(data),digest)
    return actual
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_baseline':'05e20169240ec812c988af1017cffc495319ec3c','code_commit':code,
    'tested_source':'Both 14e builds used an auditable dirty snapshot based on 05e2016. Each snapshot module matches current source bytes and the normalized Git blobs of code_commit. Final explicit ordinary suite runs at code_commit.',
    'scope':'Private complete F407 TIM1 single-FS classic CDC Ground candidate plus F103 regression. No generic admission, hardware or blocked EP0 review.',
    'families':{},'source_audit':{},'limits':['EP0 and complete asynchronous lifecycle: NOT PROVEN; b66 independent review interrupted by platform safety, no review outcome and no retry',
        'Semantic critical-contract acceptance, library/indirect call graph and recursion, main/MSP/ISR nesting stack, IRQ latency, MCU WCET and physical timing: NOT PROVEN',
        'No hardware, DAPLink, serial, flashing or START; no daily HEAD/GUI/FINAL/user-file mutation; no push or merge'],
    'normal_generation':'BLOCKED; private validation option only','parent_notification':'Source thread send returned thread not found; final delivery uses platform completion notification'}
for family in ('f103','f407'):
    build=Path('C:/Users/chdxm/AppData/Local/Temp')/('ccdi-handoff-ground-'+family+'-14e')
    receipt=json.loads((build/'receipt.json').read_text());snapshot=json.loads((build/'source-snapshot.json').read_text())
    assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED' and not receipt['warning_diagnostics'] and receipt['failure'] is None
    artifact_count=0
    for path,digest in receipt['output_artifact_sha256'].items():checked(build,path.replace('\\','/'),digest);artifact_count+=1
    for path,digest in receipt['experimental_files_sha256'].items():
        copy(checked(build,path,digest),'final/'+family+'/'+path)
    audit={}
    for path,record in snapshot['modules'].items():
        actual=checked(root/'apps/SCG',path,record['sha256']);data=actual.read_bytes()
        blob=subprocess.check_output(['git','-C',str(root),'show',code+':apps/SCG/'+path.replace('\\','/')])
        assert blob.replace(b'\r\n',b'\n')==data.replace(b'\r\n',b'\n'),path
        audit[path]={'worktree_sha256':sha(data),'git_blob_sha256':sha(blob),'equal_after_crlf_normalization':True}
        destination='source_archive/apps/SCG/'+path.replace('\\','/')
        target=stage/destination
        if target.exists():assert target.read_bytes()==data
        else:copy(actual,destination)
    for name in ('receipt.json','source-snapshot.json','commands.log','candidate_config.ssproject'):
        copy(build/name,'final/'+family+'/'+name)
    for path in ('build/native.elf','build/native.bin','build/native.map','build/native-artifact-report.json',
        'build/native-host/ready_transport_fixture.c','build/analysis/native.elf','build/analysis/native.bin','build/analysis/native.map'):
        if (build/path).is_file():copy(build/path,'final/'+family+'/'+path)
    for p in (build/'build').rglob('*.su'):copy(p,'final/'+family+'/'+p.relative_to(build).as_posix())
    facts=receipt['facts'];sdk=Path(facts['irq_evidence_source']);sdk_bytes=sdk.read_bytes()
    assert sha(sdk_bytes)==facts['irq_header_sha256']
    enumerators={name:int(value) for name,value in re.findall(r'\b(\w+_IRQn)\s*=\s*(-?\d+)\b',sdk_bytes.decode())}
    assert enumerators==dict(facts['irq_numbers'])
    component=Path(facts['evidence_source']);assert sha(component.read_bytes())==facts['evidence_sha256']
    copy(Path('D:/python_software/SilverStar/.work/ccdi_facts')/('f407-usb13.json' if family=='f407' else 'f103-usb.json'),'facts/'+family+'.json')
    gate=json.loads((work/(family+'-14e-gates.json')).read_text());assert len(gate)==4 and all(r['exit']==0 for r in gate)
    host_exes={p.relative_to(build).as_posix():sha(p.read_bytes()) for p in (build/'build/ground-host').glob('*.exe')};assert len(host_exes)==5
    manifest['families'][family]={'output':str(build),'status':receipt['status'],'compile_commands':len(receipt['commands']),
        'compiler_warning_count':0,'c_sources':len(receipt['graph']['sources']),'startup_asm_sources':len(receipt['graph']['asm_sources']),
        'generated_file_hashes':len(receipt['experimental_files_sha256']),'artifact_hashes_checked':artifact_count,
        'elf_sha256':{mode:sha((build/mode/'native.elf').read_bytes()) for mode in ('build','build/analysis')},
        'independent_sdk_header':str(sdk),'independent_sdk_sha256':sha(sdk_bytes),'independent_irq_enumerators':len(enumerators),
        'sdk_fpu_final_enumerator':enumerators.get('FPU_IRQn'),'facts_component_sha256':sha(component.read_bytes()),
        'gates':gate,'external_host_executables_sha256':host_exes,'original_native_vendor_sources':'Not duplicated in archive; immutable original hashes retained in receipt and regenerable from the frozen referenced native input'}
    manifest['source_audit'][family]=audit
    # Static equality is preservation evidence only, never EP0 acceptance.
    sys.path.insert(0,str(root/'apps/SCG/src'))
    from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
    prefix='Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c'
    original=(build/'HardwareGenerated/NativeClassicCdc'/prefix).read_text();derived=(build/'HardwareGenerated/ReviewedNativeBulk'/prefix).read_text()
    same={}
    for name in ('USBD_CDC_Setup','USBD_CDC_EP0_RxReady'):
        a,_o,b=NativeC_FunctionSpanGet(original,name);x,_o,y=NativeC_FunctionSpanGet(derived,name)
        same[name]=original[a:b]==derived[x:y];assert same[name]
    manifest['families'][family]['class_control_functions_byte_identical_normalized_text']=same
old=root/'apps/SCG/docs/evidence/native_classic_cdc_runtime_20261010'
prior=json.loads((old/'verification.json').read_text())
for path,record in prior['files'].items():checked(old,path.replace('\\','/'),record['sha256'])
manifest['p3']={'resolved_in':'05e20169240ec812c988af1017cffc495319ec3c','all_f103_prior_manifest_files_checked':len(prior['files']),
    'restored':['final/build/native-artifact-report.json','final/build/native-host/ready_transport_fixture.c']}
test=json.loads((work/'normal14d-command.json').read_text());assert test['exit']==0 and test['source_commit']==code
for path,digest in test['source_sha256'].items():checked(root,path,digest)
log=(work/'normal14d.log').read_text();assert '154 passed' in log and not re.search(r'\d+ (?:failed|skipped)',log)
trace=[json.loads(line) for line in (work/'normal14d-host-commands.jsonl').read_text().splitlines()]
assert trace and not any('exception' in r for r in trace)
manifest['ordinary_tests']={'passes':154,'skips':0,'command':test['command'],'source_commit':code,'host_subprocess_commands':len(trace),
    'expected_original_program_nonzero_exits':sum(r['exit']!=0 for r in trace),'existing_pytest_config_warning':'Unknown config option: cache_dir retained',
    'scope':test['scope'],'not_executed':['Malformed USB packets','USB owner-expression research','Blocked b66 independent EP0 review','GUI and old TF/SD/maintenance diagnostics']}
for p in work.iterdir():
    if p.is_file() and p.suffix in ('.py','.log','.json','.jsonl','.exit'):
        copy(p,('runners/' if p.suffix=='.py' else 'attempts/')+p.name)
for folder in ('timer-review-replay','timer-review-replay14e'):
    for p in (work/folder).rglob('*'):
        if p.is_file() and p.suffix!='.exe':copy(p,'models/'+folder+'/'+p.relative_to(work/folder).as_posix())
for path in ('manifest.json','dirty.diff'):copy(work/'handoff_snapshot'/path,'handoff/'+path)
temp=Path('C:/Users/chdxm/AppData/Local/Temp/ccdi-handoff-normal14d')
for record in trace:
    for path in record['input_argument_files']:
        actual=Path(path)
        if actual.is_relative_to(temp) and actual.suffix in ('.c','.h','.py'):
            copy(actual,'host_fixtures/'+actual.relative_to(temp).as_posix())
for case in temp.iterdir():
    if case.is_dir():
        for p in case.iterdir():
            if p.is_file() and p.suffix in ('.h','.c','.json','.log','.exit'):
                copy(p,'host_fixtures/'+p.relative_to(temp).as_posix())
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
versions=[]
for name,command in [('python',['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','--version']),('host_gcc',['gcc','--version']),('arm_gcc',['arm-none-eabi-gcc','--version']),('git',['git','--version']),('power10_shell',['powershell','-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()'])]:
    r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30);assert r.returncode==0
    versions.append({'name':name,'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
manifest['versions']=versions
(stage/'.gitattributes').write_text('* -text\n')
manifest['files']={p.relative_to(stage).as_posix():{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in stage.rglob('*') if p.is_file()}
(stage/'verification.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'code_commit':code,'files':len(manifest['files']),'bytes':sum(v['bytes'] for v in manifest['files'].values()),
    'host_commands':len(trace),'families':{k:{x:v[x] for x in ('compile_commands','artifact_hashes_checked','independent_irq_enumerators')} for k,v in manifest['families'].items()}},indent=2))
