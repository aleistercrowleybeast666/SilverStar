from pathlib import Path
import sys,os,json,subprocess
from datetime import datetime,timezone
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar');label=sys.argv[1]
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
 SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
 SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
 SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
 SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-formal-usb-worktree/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
 SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h')
command=[r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe','-B',str(task/'daily_backend_pytest.py'),
 'apps/SCG/tests/test_usb_ground_backend.py','apps/SCG/tests/test_native_ground_backend.py','-k','all_output_routes_block_before_write or formal_build_rejects_even_without_ensure_buildable or formal_plan_and_generation_reject_bound_model','-q','-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label]
d={'command':command,'cwd':str(repo),'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'scope':'Direct ordinary F103/F407/C071 formal generation/build/output routes refuse before writes with unchanged guards; no malformed USB or stopped safety review',
 'started_utc':datetime.now(timezone.utc).isoformat()}
with (task/(label+'.log')).open('w',encoding='utf8') as log:r=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
d.update(exit=r.returncode,finished_utc=datetime.now(timezone.utc).isoformat());(task/(label+'-command.json')).write_text(json.dumps(d,indent=2),encoding='utf8')
print((task/(label+'.log')).read_text(encoding='utf8'))
raise SystemExit(r.returncode)
