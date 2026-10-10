from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,os,sys
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar\.work\ccdi');label=sys.argv[1]
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
 SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
 SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
 SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
 SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-formal-usb-worktree/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
 SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h')
files=['test_ground_gui_cubemx_import.py','test_ground_gui_acceptance_20261009.py','test_task_progress_busy.py','test_target_compile_progress.py','test_build_progress.py','test_native_control_normal.py','test_native_machine_contract.py','test_native_clock_tim_phase.py','test_native_no_heap.py','test_native_radio.py','test_native_runtime.py','test_build_audit.py']
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B',str(task/'backend_pytest.py'),*['apps/SCG/tests/'+p for p in files],'-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,'-q']
record={'command':command,'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'dirty':subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True),'started_utc':datetime.now(timezone.utc).isoformat(),'scope':'Preserved ordinary GUI/target progress/build and native control/clock/radio/ABI/runtime regression; no hardware'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 result=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=700)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat());(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,result.returncode);print((task/(label+'.log')).read_text(encoding='utf8')[-20000:])
