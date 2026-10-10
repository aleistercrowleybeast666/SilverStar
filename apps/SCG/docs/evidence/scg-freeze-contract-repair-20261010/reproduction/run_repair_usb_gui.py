from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,subprocess,time
task=Path(__file__).parent;repo=Path(__file__).parent/'r'
label=sys.argv[1];mode=sys.argv[2] if len(sys.argv)>2 else 'short'
while (task/'repair-sequence.pause').exists(): time.sleep(1)
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
 SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
 SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
 SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
 SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-10/task/r/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
 SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h',
 SILVERSTAR_USB_BACKEND_ARM='1',SILVERSTAR_USB_BACKEND_BUILD_INDEX=str(task/(label+'-build-index.jsonl')))
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B',str(task/'repair_backend_pytest.py'),
 'apps/SCG/tests/test_usb_gui_flow.py','-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,'-q']
command+=['--junitxml='+str(task/(label+'.xml'))]
if mode=='short':command+=['-k','not success_build']
if len(sys.argv)>3:command+=['-k',sys.argv[3]]
paths=[repo/('apps/SCG/src/silverstar_fccg/'+p) for p in ('app/usb_ground_flow.py','app/usb_ground.py','app/native_ground.py','build/native_compile.py','ui/main_window.py')]
paths+=[repo/'apps/SCG/tests/test_usb_gui_flow.py']
record={'command':command,'cwd':str(repo),'started_utc':datetime.now(timezone.utc).isoformat(),'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'dirty_diff':subprocess.check_output(['git','-C',str(repo),'diff','--binary'],text=True),
 'sources':{str(p.relative_to(repo)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source':p.read_text(encoding='utf8')} for p in paths},
 'scope':'Ordinary actual GUI import/save/reload/private Plan/Export/Build, result/progress/cancel and exact-target refusal; no hardware or stopped safety review'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 run=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=700)
record.update(exit=run.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,run.returncode);print((task/(label+'.log')).read_text(encoding='utf8')[-22000:])

