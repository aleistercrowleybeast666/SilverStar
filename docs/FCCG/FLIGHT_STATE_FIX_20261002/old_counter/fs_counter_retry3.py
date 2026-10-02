from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002');out=repo/'.work/fs_counter_evidence'
prior=json.loads((out/'results_v2.json').read_text(encoding='utf8'))
text=(out/'flight_state_scheduler_host_v2.c').read_text(encoding='utf8').replace('(s_contexts[0].tx_count - s_contexts[0].tx_control_count) <= 2U','((uint32_t)s_contexts[0].tx_count - (uint32_t)s_contexts[0].tx_control_count) <= 2U')
fixture=out/'flight_state_scheduler_host_v3.c';fixture.write_text(text,encoding='utf8')
command=[str(fixture) if x.endswith('flight_state_scheduler_host_v2.c') else x for x in prior[0]['command']];command[-1]=str(out/'scheduler_v3.exe')
records=[]
for name,cmd in [('compile_v3',command)]+[(s,[command[-1],s]) for s in ['contended','no_navigation','unavailable']]:
 result=subprocess.run(cmd,cwd=prior[0]['cwd'],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=90)
 log=out/(name+'_v3.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
 records.append({'name':name,'command':cmd,'cwd':prior[0]['cwd'],'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 print(name,result.returncode,result.stdout+result.stderr,flush=True)
 if name=='compile_v3' and result.returncode:break
(out/'results_v3.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
