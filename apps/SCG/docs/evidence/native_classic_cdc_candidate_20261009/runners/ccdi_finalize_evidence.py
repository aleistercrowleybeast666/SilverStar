from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,sys
ROOT=Path('D:/python_software/SilverStar'); REPO=ROOT/'.work/ccdi'
OUT=REPO/'apps/SCG/docs/evidence/native_classic_cdc_candidate_20261009'
TEMP=Path('C:/Users/chdxm/AppData/Local/Temp')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args,repo=ROOT):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
assert git('rev-parse','HEAD')=='56448bd35736221d7885a26704f2f953b0fe5055'
assert git('branch','--show-current')=='fix/nightly-user-ready-20261003'
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
original=json.loads((ROOT/'.work/scg_ground_integration_20261009/original-files.json').read_text())
assert set(git('ls-files','--others','--exclude-standard').splitlines())=={Path(e['Path']).name for e in original}
for entry in original: assert sha(Path(entry['Path'])).upper()==entry['Hash']
frozen=json.loads((ROOT/'.work/scg_ground_integration_20261009/source-parity.json').read_text())['gui_frozen_sha256']
for p,h in frozen.items():assert sha(ROOT/p)==h,p
source=json.loads((ROOT/'.work/ccdi-evidence10b/source_snapshot.json').read_text())
for p,h in source['source_sha256'].items():
    if p not in {'apps/SCG/src/silverstar_fccg/hardware/native_classic_cdc.py',
                 'apps/SCG/tools/validation/native_classic_cdc_compile.py'}:assert sha(REPO/p)==h,p
native_log=(ROOT/'.work/ccdi-native-tests10g.log').read_text(encoding='utf-8')
assert '56 passed' in native_log and 'failed' not in native_log.lower(),native_log[-300:]
assert (ROOT/'.work/ccdi-native-tests10g.exit').read_text().strip()=='0'
legacy=(ROOT/'.work/ccdi-legacy-tests10b.log').read_text(encoding='utf-8')
baseline=(ROOT/'.work/ccdi-baseline-tests10b.log').read_text(encoding='utf-8')
assert '1 failed, 41 passed' in legacy and '1 failed' in baseline
assert 'SilverStar\\apps\\SCG\\src' in baseline and 'sd_sdio_fatfs_f1' in baseline
gates=json.loads((ROOT/'.work/ccdi-evidence10b/emitted-gates.json').read_text())
assert len(gates['results'])==3 and all(r['exit']==0 and r['critical_contract_not_proven'] for r in gates['results'])
assert not OUT.exists(),OUT
OUT.mkdir(parents=True)
manifest={}
def copy(p,name):
    target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    manifest[name]={'origin':str(p),'sha256':sha(target),'bytes':target.stat().st_size}
for p in sorted((ROOT/'.work').glob('ccdi-native-tests10*.log')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-native-tests10*.exit')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-native-f*-10*.log')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-native-f*-10*.exit')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-legacy-tests10*.log')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-legacy-tests10*.exit')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-baseline-tests10*.log')):copy(p,'attempts/'+p.name)
for p in sorted((ROOT/'.work').glob('ccdi-baseline-tests10*.exit')):copy(p,'attempts/'+p.name)
copy(ROOT/'.work/ccdi-evidence-finalize.log','attempts/ccdi-evidence-finalize10a.log')
copy(ROOT/'.work/ccdi-evidence-finalize.exit','attempts/ccdi-evidence-finalize10a.exit')
for p in (ROOT/'.work/ccdi-evidence10b').glob('*'):
    if p.is_file():copy(p,'legacy/'+p.name)
for p in (ROOT/'.work/ccdi-evidence10b/source_snapshot').rglob('*'):
    if p.is_file():copy(p,'legacy/source_snapshot/'+p.relative_to(ROOT/'.work/ccdi-evidence10b/source_snapshot').as_posix())
copy(TEMP/'sscdc-legacy10b/generation.json','legacy/generation.json')
for name in ('ccdi_run.py','ccdi_baseline_run.py','ccdi_prepare_facts.py','ccdi_legacy_generate.py',
             'ccdi_legacy_gates.py','ccdi_legacy_generate10b.py','ccdi_legacy_gates10b.py'):
    copy(ROOT/'.work'/name,'runners/'+name)
copy(Path(__file__),'runners/ccdi_finalize_evidence.py')
copy(ROOT/'.work/scg_ground_integration_20261009/generate_v2.py','runners/original_generate_v2.py')
copy(ROOT/'.work/scg_ground_integration_20261009/run_gates.py','runners/original_run_gates.py')
for name in ('normal_test_paths','closeout_test_paths'):
    copy(ROOT/('docs/evidence/nightly_software_20261008/'+name+'.py'),'runners/'+name+'.py')
native=[]
for case in ('f103','f407'):
    for attempt in ('10a','10b','10c','10d','10e','10f'):
        directory=TEMP/('sscdc-native-'+case+'-'+attempt)
        if (directory/'receipt.json').is_file():
            copy(directory/'receipt.json','native/'+case+'/'+attempt+'/receipt.json')
            copy(directory/'commands.log','native/'+case+'/'+attempt+'/commands.log')
    directory=TEMP/('sscdc-native-'+case+'-10f')
    receipt=json.loads((directory/'receipt.json').read_text())
    assert receipt['status']=='FAILED' and receipt['no_warning_gate']=='FAIL'
    assert (ROOT/'.work'/('ccdi-native-'+case+'-10f.exit')).read_text().strip()=='1'
    assert 'strict no-warning acceptance FAILED' in receipt['failure']
    assert receipt['new_module_sha256']==sha(REPO/'apps/SCG/src/silverstar_fccg/hardware/native_classic_cdc.py')
    assert receipt['validation_script_sha256']==sha(REPO/'apps/SCG/tools/validation/native_classic_cdc_compile.py')
    assert all(c['exit']==0 for c in receipt['commands'])
    assert len(receipt['warning_diagnostics'])==2
    for p,h in receipt['output_artifact_sha256'].items():assert sha(directory/p)==h,p
    native.append({'case':case,'status':receipt['status'],'receipt_sha256':sha(directory/'receipt.json'),
                   'output':str(directory),'commands':len(receipt['commands']),
                   'native_c_units':len(receipt['contract']['build']['sources']),
                   'asm_units':len(receipt['graph']['asm_sources']),
                   'probe_units':1,'toolchain':receipt['toolchain_version'],
                   'warning_diagnostics':receipt['warning_diagnostics'],'no_warning_gate':'FAIL','exit':1,
                   'artifact_hashes':receipt['output_artifact_sha256']})
review=Path('C:/Users/chdxm/Documents/Codex/2026-10-09/task-2/c071-ep0-independent/review.md')
receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'branch':git('branch','--show-current',repo=REPO),
 'source_commit':source['head'],'legacy_source_snapshot':source,'daily_head':git('rev-parse','HEAD'),
 'final_source_sha256':{p:sha(REPO/p) for p in source['source_sha256']},
 'gui_i18n_unchanged':len(frozen),'user_files_unchanged':original,'native':native,
 'native_tests':{'passed':56,'failed':0,'skipped':0,'exit':0,'log':'attempts/ccdi-native-tests10g.log'},
 'native_test_command':[str(ROOT/'apps/FLP/.venv/Scripts/python.exe'),'-B',str(ROOT/'.work/ccdi_run.py'),'-q',
    str(REPO/'apps/SCG/tests/test_native_classic_cdc.py'),'--basetemp='+str(TEMP/'nc10g')],
 'test_environment':{'QT_QPA_PLATFORM':'offscreen','PYTHONDONTWRITEBYTECODE':'1',
    'SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT':'C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation'},
 'legacy_tests':{'passed':41,'failed':1,'exit':1,'baseline_reproduced':True,
                 'failure':'test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources: existing SD/F1 SD physical identity collision'},
 'fresh_emitted_legacy_gates':gates,
 'tools':{'python':sys.version,'git':git('--version'),
          'host_gcc':subprocess.check_output(['D:/msys64/ucrt64/bin/gcc.exe','--version'],text=True).splitlines()[0],
          'make':subprocess.check_output(['D:/msys64/ucrt64/bin/mingw32-make.exe','--version'],text=True).splitlines()[0],
          'dependency_checker_sha256':sha(REPO/'apps/SCG/plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools/ground_artifact_contract.py')},
 'external_ep0_review':{'path':str(review),'sha256':sha(review)},
 'attempt_notes':{
   'native_tests10a':'4 failed / 38 passed: Windows cached path limit and test mutation encoding errors; retained.',
   'native_tests10b':'4 failed / 40 passed: serialization normalization and exception wrapper gaps; retained.',
   'native_tests10c':'2 failed / 42 passed: incorrect test assumption that saving creates no Ground_Station descriptor folder; corrected to before/after byte equality.',
   'native_tests10d':'44 passed for the earlier 44-case scope, not the final revision.',
   'native_tests10e-pre':'4 failed / 4 passed / 44 deselected: demonstrated accepted Make append and unparsed MEMORY expression before correction.',
   'native_tests10e':'Own session 36666 interrupted with Ctrl-C, returned exit 1; incomplete, not a pass. Overlarge remaining-quota read buffer caused excessive CPU/memory.',
   'native_tests10f':'Own session 97766 interrupted with Ctrl-C, returned exit 1; incomplete, not a pass. Same pre-buffer-fix implementation.',
   'native_compile10a':'Both failed on const transmitter-buffer declaration mismatch in validator probe.',
   'native_compile10b':'Both completed earlier native build scope; not final-source evidence.',
   'native_compile10c':'Both rejected legitimate native weak Reset_Handler due to an overstrict new validator condition; IRQ strong requirements were not relaxed.',
   'native_compile10d':'Both completed before bounded-file-read refinement; not final-source evidence.',
   'native_compile10e':'Both compile/link command sets exited zero but each emitted two vendor UART analyzer warnings; earlier no-warning commentary was corrected. These are not acceptance passes.',
   'baseline_tests10a':'Runner prepended isolated package; excluded from baseline claims. baseline_tests10b prints actual daily package path.'},
 'archived_files':manifest,
 'limitations':'CANDIDATE ONLY. Runtime generation unconditionally rejected. EP0 unsafe/unreviewed originals are not accepted for runtime. No complete generic backend, no entire-suite PASS, no hardware/stack/WCET/manual critical-contract acceptance. Prior-attempt results retain their exact separate scopes.'}
(OUT/'verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print('Evidence finalized',OUT,'verification SHA256',sha(OUT/'verification.json'),flush=True)
