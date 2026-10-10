from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

task = Path(__file__).resolve().parent
root = Path(r'D:\python_software\SilverStar\.work\ccdi')
label = sys.argv[1]
selection = sys.argv[2] if len(sys.argv) > 2 else 'model'
env = os.environ.copy()
env['PATH'] = 'D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;' + env.get('PATH', '')
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', QT_QPA_PLATFORM='offscreen',
    SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
    SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
    SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
    SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-formal-usb-worktree/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
    SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h')
env.update(SILVERSTAR_USB_BACKEND_ARM='1' if selection=='all' else '0',
    SILVERSTAR_USB_BACKEND_BUILD_INDEX=str(task / (label+'-build-index.jsonl')))
command = ['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe', '-B', str(task / 'backend_pytest.py'),
    'apps/SCG/tests/test_usb_ground_backend.py', '-p','no:cacheprovider',
    '--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label, '-q']
if selection != 'all':
    command += ['-k','not real_']
if len(sys.argv)>3:
    command += ['-k',sys.argv[3]]
paths = ['apps/SCG/src/silverstar_fccg/app/usb_ground.py',
    'apps/SCG/src/silverstar_fccg/app/service.py',
    'apps/SCG/src/silverstar_fccg/generator/multi_target.py',
    'apps/SCG/tests/test_usb_ground_backend.py']
paths += [p.relative_to(root).as_posix() for p in (root/'apps/SCG/src/silverstar_fccg/hardware/usb_profiles').iterdir()]
record = {'command':command,'cwd':str(root),'started_utc':datetime.now(timezone.utc).isoformat(),
    'source_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
    'scope':'Ordinary exact-target model/native/companion byte-identity and dispatch checks; no USB packets, owner expressions, blocked review or hardware',
    'sources':{p:{'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest(),
        'source':(root/p).read_text(encoding='utf-8')} for p in paths},
    'dirty_diff':subprocess.check_output(['git','-C',str(root),'diff','--binary'],text=True),
    'inputs':{key:value for key,value in env.items() if key.startswith('SILVERSTAR_')}}
receipt=task/(label+'-command.json')
receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
with (task/(label+'.log')).open('w',encoding='utf-8') as stream:
    completed=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
record.update(exit=completed.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
print(label,completed.returncode)
print((task/(label+'.log')).read_text(encoding='utf-8')[-22000:])
