from pathlib import Path
import os,sys,subprocess,json,datetime,hashlib
root=Path('D:/python_software/SilverStar/.work/ccdi');out=Path(__file__).resolve().parent
label=sys.argv[1]
paths=['apps/SCG/tests/'+name+'.py' for name in (
    'test_native_clock','test_native_clock_tim','test_native_clock_tim_phase','test_native_clock_tim_lifecycle',
    'test_native_clock_tim_callers','test_native_runtime','test_native_pc','test_native_radio',
    'test_native_machine_contract','test_native_probe_gate','test_native_usb_indexed_ll','test_native_ground_data_path')]
paths+=['apps/SCG/tests/test_native_platform.py::test_generated_platform_runtime_boundaries',
    'apps/SCG/tests/test_native_usb_ll.py']
for scenario in ('normal','open1','open2','open3','app-init','prepare-init','tx-fail','tx-busy','rearm','receive','zlp','close'):
    paths+=['apps/SCG/tests/test_native_usb_indexed.py::test_actual_indexed_bulk_pipeline_and_faults['+scenario+']',
        'apps/SCG/tests/test_native_usb_data.py::test_real_native_bulk_functions_propagate_failure['+scenario+']']
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen',SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',SILVERSTAR_NATIVE_GROUND_OUTPUT='C:/Users/chdxm/AppData/Local/Temp/ccdi-handoff-ground-f407-14e')
env['CCDI_COMMAND_TRACE']=str(out/(label+'-host-commands.jsonl'))
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B',
    str(out/'trace_pytest.py'),
    *paths,'-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/ccdi-handoff-'+label,'-q']
modules={}
for directory in ('apps/SCG/src/silverstar_fccg/generator','apps/SCG/tests'):
    for p in (root/directory).glob('native*.py' if 'generator' in directory else 'test_native*.py'):
        modules[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
record={'command':command,'cwd':str(root),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
    'source_sha256':modules,'scope':'Explicit ordinary clock/runtime/platform/radio/data/API-return tests; no malformed USB packets, owner-expression research or blocked EP0 review'}
(out/(label+'-command.json')).write_text(json.dumps(record,indent=2))
with (out/(label+'.log')).open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
record['exit']=result.returncode;record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(out/(label+'-command.json')).write_text(json.dumps(record,indent=2))
(out/(label+'.exit')).write_text(str(result.returncode));print('ordinary suite',label,result.returncode)
