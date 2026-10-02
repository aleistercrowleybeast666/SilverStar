from pathlib import Path
import hashlib, json, os, subprocess, sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
workspace=Path(__file__).parent
root=repo/'.work/fs_counter'; evidence=repo/'.work/fs_counter_evidence'
if root.exists() or evidence.exists(): raise FileExistsError('Preserve prior evidence')
evidence.mkdir(parents=True)
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
baseline=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002\.work\imu_final\Flight_Controller\SilverStar.ssproject')
config=json.loads(baseline.read_text(encoding='utf8')); config['project']['name']='SS_FlightStateCounter_20261002'
inp=evidence/'Input.ssproject'; inp.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
TargetGeneration_Apply(service.Project_Open(inp),service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
project=root/'Flight_Controller'
head=(repo/'apps/FCCG/tests/fixtures/radio_handshake_host.c').read_text(encoding='utf8').split('static void Test_AckBacklog(void)')[0]
head=head.replace('#include "test_telemetry.c"','#define Estimator_GetLatestSnapshot Test_PreviousEstimatorSnapshot\n#include "test_telemetry.c"\n#undef Estimator_GetLatestSnapshot')
head=head.replace('static TestFrame s_over_air[128];','static uint32_t s_simulated_tx_end_ms;\nstatic TestFrame s_over_air[128];')
head=head.replace('(void)instance; (void)timeout;\n    TEST_CHECK(length', '(void)timeout;\n    s_simulated_tx_end_ms = s_tick_ms + Lora_PacketAirtimeMs(&s_contexts[instance], length);\n    TEST_CHECK(length')
head=head.replace('#include "telemetry_service.c"',(workspace/'fs_counter_cases.c').read_text(encoding='utf8')+'\n#include "telemetry_service.c"')
head=head.replace('LORA_RF_FREQUENCY_HZ == 2473000000UL','LORA_RF_FREQUENCY_HZ == 2395000000UL')
fixture=evidence/'flight_state_scheduler_host.c'; fixture.write_text(head+(workspace/'fs_counter_main.c').read_text(encoding='utf8'),encoding='utf8')
includes=[p for p in project.rglob('Inc') if 'build' not in p.parts]
includes += [project/p for p in ['System/User','Tests/Host','Devices/Telemetry/SX1281/Src','Modules/Src','Middlewares/Third_Party/SX1280lib']]
command=[r'D:\msys64\ucrt64\bin\gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-DSILVERSTAR_AIR_LINK_ENABLED=1','-include',str(project/'Generated/Inc/project_flight_config.h')]
for path in includes: command+=['-I',str(path)]
command += [str(fixture)] + [str(project/p) for p in ['Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c','Generated/Src/project_resources.c','Protocol/Src/air_protocol.c','Common/Src/silverstar_assert.c','System/Calibration/Src/system_calibration_correction.c']]
exe=evidence/'scheduler.exe';command+=['-lm','-o',str(exe)]
records=[]
for name,cmd in [('compile',command)]+[(s,[str(exe),s]) for s in ['contended','no_navigation','unavailable']]:
 result=subprocess.run(cmd,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=90)
 log=evidence/(name+'.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
 records.append({'name':name,'command':cmd,'cwd':str(project),'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 print(name,result.returncode,result.stdout+result.stderr,flush=True)
 if name=='compile' and result.returncode: break
(evidence/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
