from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,subprocess,hashlib,time
task=Path(__file__).parent;repo=Path(__file__).parent/'r';group=sys.argv[1];label=sys.argv[2]
groups={
 'backend':['test_usb_ground_backend.py','test_native_ground_backend.py'],
 'gui_native':['test_ground_gui_cubemx_import.py','test_ground_gui_acceptance_20261009.py','test_task_progress_busy.py','test_target_compile_progress.py','test_build_progress.py','test_native_control_normal.py','test_native_machine_contract.py','test_native_clock_tim_phase.py','test_native_no_heap.py','test_native_radio.py','test_native_runtime.py','test_build_audit.py','test_native_clock_tim.py','test_native_clock_tim_lifecycle.py','test_native_clock_tim_callers.py','test_native_clock.py','test_usb_lifecycle_normal.py'],
 'uart':['test_ground_backpressure.py','test_ground_board_recovery.py','test_ground_bridge_bounds.py','test_ground_cubemx_base.py','test_ground_generated_gates.py','test_ground_generated_runtime.py','test_ground_pc_uart_dma.py','test_ground_radio_hal.py','test_ground_radio_runtime.py','test_ground_activity_configuration.py','test_ground_schema_contract.py','test_uart_async_host.py','test_uart_recovery_host.py'],
 'flight':['test_physical_device_platform_identity.py','test_project_catalog_cache.py','test_plugin_security.py','test_internal_platform_refactor.py','test_generator_integration.py','test_round2_targets.py','test_flight_state_scheduler_generated_host.py','test_firmware_identity_gate.py','test_firmware_artifact_protocols.py','test_runtime_safety.py','test_stack_budget.py','test_power_of_ten_checker_paths.py','test_quality_manual_acceptance.py','test_target_quality_checks.py'],
}
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
 SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
 SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
 SILVERSTAR_C071_NATIVE='C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
 SILVERSTAR_C071_COMPANION='C:/Users/chdxm/Documents/Codex/2026-10-10/task/r/apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',
 SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h',
 SILVERSTAR_NATIVE_BACKEND_ARM='1',SILVERSTAR_USB_BACKEND_ARM='1',SILVERSTAR_USB_BACKEND_BUILD_INDEX=str(task/(label+'-build-index.jsonl')),
 SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX=str(task/(label+'-private-build-index.jsonl')))
while (task/'repair-sequence.pause').exists(): time.sleep(1)
files=['apps/SCG/tests/'+p for p in groups[group]]
for p in files:assert (repo/p).is_file(),p
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
tree=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD:apps/SCG'],text=True).strip()
assert not subprocess.check_output(['git','-C',str(repo),'diff','--name-only'],text=True).strip(), 'Uncommitted repair code changed; inspect before testing'
command=[r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe','-B',str(task/'repair_backend_pytest.py'),*files,'-q','-p','no:cacheprovider',
 '--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,'--junitxml='+str(task/(label+'.xml'))]
d={'command':command,'cwd':str(repo),'source_commit':head,'scg_tree':tree,'group':group,'complete_modules':files,
 'source_status':subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).splitlines(),
 'test_sha256':{p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in files},
 'scope':'Authorized isolated code repair, all cases in explicitly listed normal product modules, no -k or deselection. Temp/offscreen only. Blocked malformed USB/owner-expression review modules deliberately excluded. No source edits/hardware.',
 'known_baseline':'Original six failures/twelve skips at 2b3d4ae retained in fz receipts; repaired producer/consumer contracts and setup are tested, no xfail or guard relaxation',
 'started_utc':datetime.now(timezone.utc).isoformat()}
(task/(label+'-command.json')).write_text(json.dumps(d,indent=2),encoding='utf8')
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 try:r=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800);d['exit']=r.returncode
 except subprocess.TimeoutExpired:d['exit']='TIMEOUT';raise
 finally:
  d.update(finished_utc=datetime.now(timezone.utc).isoformat(),ending_head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
   ending_scg_tree=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD:apps/SCG'],text=True).strip());(task/(label+'-command.json')).write_text(json.dumps(d,indent=2),encoding='utf8')
print(label,d['exit']);print((task/(label+'.log')).read_text(encoding='utf8')[-2200:])

