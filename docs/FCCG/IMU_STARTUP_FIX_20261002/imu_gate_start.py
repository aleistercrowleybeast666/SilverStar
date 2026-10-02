from pathlib import Path
import sys, os, subprocess, json, hashlib, shutil, datetime
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
review=repo/'.work/imu_trace_review'
files=[
repo/'apps/FCCG/plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Src/jy901b_device.c',
repo/'apps/FCCG/plugins/builtin/silverstar_mcu_family_stm32f4/payload/Platform/STM32F4/Src/platform_uart_stm32f4.c',
repo/'apps/FCCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc/platform_uart.h',
repo/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1']
# Preserve optional trace separately before restoring these exact task-owned edits.
for path in files:
    saved=review/('diagnostic_'+path.name)
    if saved.exists():raise FileExistsError(saved)
    shutil.copy2(path,saved)
    shutil.copy2(review/('original_'+path.name),path)
shutil.copy2(Path(__file__).with_name('test_jy901b_register_stream_host.py'),repo/'apps/FCCG/tests/test_jy901b_register_stream_host.py')
root=repo/'.work/imu_final'
out=repo/'.work/imu_final_evidence'
if root.exists() or out.exists():raise FileExistsError('Preserve previous output')
out.mkdir(parents=True)
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
config=json.loads((repo/'.work/imu_repair_evidence/Input.ssproject').read_text(encoding='utf8'))
config['project']['name']='SS_ImuStartupRepair_Final_20261002'
inp=out/'Input.ssproject';inp.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
TargetGeneration_Apply(service.Project_Open(inp),service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG/tests')+';'+str(repo/'apps/FCCG'))
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
results=[]
def run(name,command,cwd,environment=env):
    log=out/(name+'.log');start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with log.open('w',encoding='utf8') as f:
        result=subprocess.run(command,cwd=cwd,env=environment,stdout=f,stderr=subprocess.STDOUT)
    item={'name':name,'command':command,'cwd':str(cwd),'exit':result.returncode,'log':str(log),'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    results.append(item);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
    print(json.dumps(item),flush=True);print(log.read_text(encoding='utf8',errors='replace')[-1400:],flush=True)
project=root/'Flight_Controller'
old=json.loads((repo/'.work/imu_repair_evidence/stream_results_v2.json').read_text(encoding='utf8'))
cmd=[x.replace(str(repo/'.work/imu_repair/Flight_Controller'),str(project)) for x in old[0]['command']]
cmd[-1]=str(out/'stream.exe')
run('compile_stream',cmd,project)
if results[-1]['exit']==0:run('stream',[cmd[-1]],project)
baseline=json.loads((repo/'.work/imu_counter_evidence2/results_v2.json').read_text(encoding='utf8'))
cmd=[x.replace(str(repo/'.work/imu_counter/Flight_Controller'),str(project)) for x in baseline[0]['command']]
cmd[-1]=str(out/'counter.exe')
run('compile_original_counter',cmd,project)
if results[-1]['exit']==0:run('original_counter_fixed',[cmd[-1]],project)
testenv=dict(env,SILVERSTAR_BOOT_PROBE_PROJECT=str(project),SILVERSTAR_UART_TEST_PROJECT=str(project),SILVERSTAR_UART_TEST_SOURCE=str(project/'Platform/STM32F4/Src'))
run('targeted_regression',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/imu_final_pytest'),
'apps/FCCG/tests/test_jy901b_register_stream_host.py','apps/FCCG/tests/test_jy901b_boot_probe_host.py','apps/FCCG/tests/test_jy901b_startup.py','apps/FCCG/tests/test_uart_async_host.py','apps/FCCG/tests/test_uart_recovery_host.py','apps/FCCG/tests/test_power_of_ten_checker_paths.py'],repo,testenv)
for name,targets in [('Release',['all']),('Host',['host-tests']),('architecture',['architecture-check']),('PoT',['power10-check']),('analyzer',['static-analysis']),('artifact',['artifact-check']),('resources',['stack-report','memory-report'])]:
    run(name,[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),*targets],project)
if any(item['exit'] for item in results):sys.exit(1)
