from pathlib import Path
import os,json,subprocess,sys,hashlib
from datetime import datetime,timezone
task=Path(__file__).parent
repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
label=sys.argv[1]
env=os.environ.copy()
env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
 SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
 SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
 SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
 SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-formal-usb-worktree/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
 SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h')
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B',str(task/'backend_pytest.py'),'apps/SCG/tests/test_usb_lifecycle_normal.py','-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,'-q']
record={'command':command,'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'started_utc':datetime.now(timezone.utc).isoformat(),'scope':'Only valid ordinary single-FS CDC enumeration, configured bulk transfers, ZLP, lifecycle cancellation, buffer lifetime and session reconnection through real generated USB sources. Host LL controller substitutes; no malformed USB/owner expressions or blocked independent review.', 'test_sha256':hashlib.sha256((repo/'apps/SCG/tests/test_usb_lifecycle_normal.py').read_bytes()).hexdigest()}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 result=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,result.returncode)
print((task/(label+'.log')).read_text(encoding='utf8')[-14000:])
