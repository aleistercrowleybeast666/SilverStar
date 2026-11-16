from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
P=argparse.ArgumentParser();P.add_argument('candidate');P.add_argument('target',choices=['Flight_Controller','Ground_Station']);P.add_argument('--configs',nargs='+',default=['Release','Debug']);P.add_argument('--gates',nargs='+',default=['all','artifact-check','architecture-check','power10-check','static-analysis']);a=P.parse_args()
ROOT=Path('D:/python_software/SilverStar');W=ROOT/'.work/platform-finish-20261116/boards';target=W/a.candidate/a.target
env=os.environ.copy();env['PYTHONUTF8']='1';env['PYTHONDONTWRITEBYTECODE']='1'
env['PATH']='D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;'+str(ROOT/'.venv/Scripts')+';'+env['PATH']
make='D:/msys64/ucrt64/bin/mingw32-make.exe';output=W/(a.candidate+'-'+a.target+'-final-validation');output.mkdir(exist_ok=False)
receipt={'target':str(target),'hardware_tested':False,'commands':[],'source_inputs':{}}
for p in target.rglob('*'):
 rel=p.relative_to(target)
 if p.is_file() and rel.parts[0] not in ('build','.eide','.vscode'):
  receipt['source_inputs'][rel.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
for config in a.configs:
 for gate in a.gates:
  cmd=[make,'-C',str(target),'-j2','CONFIG='+config,gate]
  if a.target=='Flight_Controller':cmd.append('GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin')
  log=output/(config+'-'+gate+'.log');before=time.monotonic()
  with log.open('w',encoding='utf8') as f:
   f.write('COMMAND '+json.dumps(cmd)+'\n');f.flush();result=subprocess.run(cmd,env=env,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  row={'argv':cmd,'config':config,'gate':gate,'exit_code':result.returncode,'seconds':time.monotonic()-before,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
  receipt['commands'].append(row);(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(config,gate,result.returncode,flush=True)
receipt['inputs_unchanged']=all((target/rel).exists() and hashlib.sha256((target/rel).read_bytes()).hexdigest()==sha for rel,sha in receipt['source_inputs'].items())
receipt['artifacts']={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (target/'build').rglob('*.elf')}
(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');sys.exit(0 if receipt['inputs_unchanged'] and all(r['exit_code']==0 for r in receipt['commands']) else 1)
