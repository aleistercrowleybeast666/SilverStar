from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002');out=repo/'.work/fs_counter_evidence'
prior=json.loads((out/'results_v3.json').read_text(encoding='utf8'))
text=(out/'flight_state_scheduler_host_v3.c').read_text(encoding='utf8')
text=text.replace('LORA_RF_FREQUENCY_HZ == 2395000000UL','LORA_RF_FREQUENCY_HZ == AIR_LINK_FREQUENCY_HZ')
text=text.replace('s_navigation_preparation.algorithm_id = 1U;','s_navigation_preparation.algorithm_id = 1U;\n    s_navigation_preparation.initialized = 1U;\n    s_calibration_status_result = SYSTEM_DEVICE_OK;\n    s_alignment_status_result = SYSTEM_DEVICE_OK;')
text=text.replace('Flight_Init(); s_imu_sample.valid_mask = 0U; Flight_Run(1500U);','}\nstatic void Flight_NoImu(void)\n{\n    Flight_Init(); s_imu_sample.valid_mask = 0U; Flight_Run(1500U);')
text=text.replace('else if (strcmp(argv[1], "unavailable") == 0) { Flight_Unavailable(); }','else if (strcmp(argv[1], "unavailable") == 0) { Flight_Unavailable(); }\n    else if (strcmp(argv[1], "no_imu") == 0) { Flight_NoImu(); }')
fixture=out/'flight_state_scheduler_host_v4.c';fixture.write_text(text,encoding='utf8')
command=[str(fixture) if x.endswith('flight_state_scheduler_host_v3.c') else x for x in prior[0]['command']];command[-1]=str(out/'scheduler_v4.exe')
records=[]
for name,cmd in [('compile_v4',command)]+[(s,[command[-1],s]) for s in ['contended','no_navigation','unavailable','no_imu']]:
 result=subprocess.run(cmd,cwd=prior[0]['cwd'],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=90)
 log=out/(name+'_v4.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
 records.append({'name':name,'command':cmd,'cwd':prior[0]['cwd'],'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 print(name,result.returncode,(result.stdout+result.stderr)[:2000],flush=True)
 if name=='compile_v4' and result.returncode:break
(out/'results_v4.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
