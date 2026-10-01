from pathlib import Path
import subprocess,hashlib,json,sys,os
root=Path(__file__).resolve().parents[2]
out=Path(__file__).parent
stage=sys.argv[1]
proof=out/('CrossGroup_'+stage);proof.mkdir(exist_ok=False)
prior=json.loads((out/'history_fault_proof.json').read_text(encoding='utf-8'))[1]
command=prior['command'][:-1]+[str(proof/'sf6.exe')]
sources=[Path(p) for p in command if p.endswith('.c')]
for source in sources:
    (proof/source.name).write_bytes(source.read_bytes())
header=root/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Inc/navigation_sf6.h'
(proof/header.name).write_bytes(header.read_bytes())
compile=subprocess.run(command,capture_output=True,env=dict(os.environ,TEMP=str(proof),TMP=str(proof)))
(proof/'compile.log').write_bytes(compile.stdout+compile.stderr)
report=dict(command=command,compile_exit=compile.returncode,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip())
if compile.returncode==0:
    result=subprocess.run([str(proof/'sf6.exe')],capture_output=True,timeout=30)
    report['run_exit']=result.returncode
    (proof/'run.log').write_bytes(result.stdout+result.stderr)
report['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in proof.iterdir() if p.is_file()}
(proof/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(report['compile_exit'],report.get('run_exit'))
