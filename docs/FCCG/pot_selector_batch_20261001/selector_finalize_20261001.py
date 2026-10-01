from pathlib import Path
import datetime, hashlib, json, os, subprocess, sys
r=Path(__file__).resolve().parents[3]; o=r/'docs/FCCG/pot_selector_batch_20261001'; w=r/'.work/SelectorSafety_70ce20d_20261001_v1'; core=r/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload'
original=json.loads((o/'result.json').read_text()); results=[]
def run(name,cmd):
    result=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=180)
    log=o/(name+'.log'); log.write_text(result.stdout+result.stderr,encoding='utf-8')
    results.append({'name':name,'command':cmd,'exit_code':result.returncode,'log':str(log.relative_to(r)),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name,result.returncode,flush=True);return result.returncode
includes=[w/'baseline/Flight_Controller/System/Src',r/'apps/FCCG/tests/fixtures/source_selector',core/'Tests/Host',core/'Common/Inc',core/'Common/Src',core/'Interfaces/Inc',core/'System/Inc',core/'System/Calibration/Inc',r/'apps/FCCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc']
cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U','-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
for path in includes:cmd+=['-I',str(path)]
exe=w/'baseline_contract_final.exe';cmd+=[str(r/'apps/FCCG/tests/fixtures/source_selector_contract_host.c'),'-o',str(exe)]
assert run('baseline_final_contract_compile',cmd)==0
cases=[(str(k),s) for k in range(1,4) for s in ['init_order','init_result','start_order','start_count','start_result','failed_restart','init_capacity','normal']]
cases += [('0',s) for s in ['gnss_count','gnss_active','gnss_position','gnss_order','next_count','next_position','next_order','next_result','health_count','health_active','health_timeout']]
cases += [('3','next_failed_restart'),('2','start_active'),('2','start_position')]
for kind,scenario in cases:run('baseline_final_'+kind+'_'+scenario,[str(exe),kind,scenario])
assert run('after_pytest_final',[sys.executable,'-m','pytest','apps/FCCG/tests/test_source_selector_contract_host.py','apps/FCCG/tests/test_device_startup_fsm.py','apps/FCCG/tests/test_neo_m9n_startup.py','apps/FCCG/tests/test_jy901b_startup.py','apps/FCCG/tests/test_power_of_ten_checker_paths.py','-q','--basetemp='+str(w/'pytest_final'),'-o','cache_dir='+str(w/'pytest_final_cache')])==0
assert hashlib.sha256((core/'System/Src/system_source_selector.c').read_bytes()).hexdigest()==original['source_sha256'][str((core/'System/Src/system_source_selector.c').relative_to(r))]
data={'head':original['head'],'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'results':results,'firmware_unchanged_from_full_build_snapshot':True,'original_full_checks':'result.json','final_test_sha256':{str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [r/'apps/FCCG/tests/fixtures/source_selector_contract_host.c',r/'apps/FCCG/tests/test_source_selector_contract_host.py']},'baseline_failed_cases':sum(x['exit_code']!=0 for x in results if x['name'].startswith('baseline_final_') and x['name']!='baseline_final_contract_compile'),'baseline_passed_cases':sum(x['exit_code']==0 for x in results if x['name'].startswith('baseline_final_') and x['name']!='baseline_final_contract_compile'),'blockers':['Flight strict Power of Ten remains FAIL with 171 gaps','Hardware and whole-program task/library/MSP/ISR stack/timing qualification NOT PROVEN'],'skips':[]}
(o/'verification_final.json').write_text(json.dumps(data,indent=2),encoding='utf-8');(o/'final_source_snapshot.diff').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=r)); print('FINAL COMPLETE',flush=True)
