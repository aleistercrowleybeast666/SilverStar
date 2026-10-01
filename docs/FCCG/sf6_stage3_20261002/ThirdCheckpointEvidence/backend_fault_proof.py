from pathlib import Path
import subprocess,json,hashlib,ctypes,sys,os
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
stage=sys.argv[1];dest=out/('BackendFault_'+stage);dest.mkdir(exist_ok=False)
command=json.loads((out/'backend_export_v3_results.json').read_text(encoding='utf-8'))['command']
command=[item for item in command if item!='-DTEST_SF6_BACKEND_EXPORT=1' and not item.endswith('/test_sf6_backend.c') and not item.endswith('\\test_sf6_backend.c') and not item.endswith('/navigation_sf6_backend.c') and not item.endswith('\\navigation_sf6_backend.c')]
command=command[:-2]+[str(root/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Tests/Host/test_sf6_backend_faults.c'),'-o',str(dest/'faults.exe')]
ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
result=subprocess.run(command,capture_output=True,env=dict(os.environ,TEMP=str(dest),TMP=str(dest)))
(dest/'compile.log').write_bytes(result.stdout+result.stderr)
report=dict(command=command,compile_exit=result.returncode,cases=[])
for name in ('navigation_sf6_backend.c','navigation_sf6.c'):
    source=root/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src'/name
    (dest/name).write_bytes(source.read_bytes())
if result.returncode==0:
    for case in ('q_nonfinite','q_nonunit','baro_flag','baro_reference'):
        tested=subprocess.run([str(dest/'faults.exe'),case],capture_output=True,timeout=10)
        (dest/(case+'.log')).write_bytes(tested.stdout+tested.stderr)
        report['cases'].append(dict(case=case,exit_code=tested.returncode))
report['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
(dest/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report)
