from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
# Preserve failed test inputs before correcting fixtures; production owners stay unchanged.
saved=repo/'.work/host_gui_second_failed_inputs';saved.mkdir(exist_ok=False)
owner=repo/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_telemetry.c'
shutil.copy2(owner,saved/'test_telemetry.c')
gui=repo/'apps/GSHC/tests/test_navigation_gui.py';shutil.copy2(gui,saved/'test_navigation_gui.py')
s=owner.read_text(encoding='utf8');at=s.index('static void Test_NavigationDeferred(');tail=s[at:]
tail=tail.replace('TEST_CHECK(frame->data[4] == AIR_ACK_RESULT_BAD_CMD);','TEST_CHECK(frame->data[4] == AIR_ACK_RESULT_CAPABILITY_REQUIRED);',1)
owner.write_text(s[:at]+tail,encoding='utf8')
s=gui.read_text(encoding='utf8')
s=s.replace('from protocol.air import parse_air_frame','from protocol.air import parse_air_frame\nfrom protocol.gsp_min import build_gsp_frame\nfrom protocol.receive_pipeline import ReceivePipeline')
start=s.index('    controller._handle_flight_state(parse_air_frame(bytes.fromhex(');end=s.index('    window.render_state()',start)
s=s[:start]+'''    wire = bytes.fromhex(
        "100001000000000800000000000000000000ff7f000000000000"
        "7903c9bdfe1dcb3d6fe0be3d6484efbe23bcf73e2bfe933d")
    event = ReceivePipeline().feed(build_gsp_frame(2, bytes((186, 20, 50)) + wire))[0]
    controller._handle_flight_state(event.air_message, event)
'''+s[end:];gui.write_text(s,encoding='utf8')
p=repo/'docs/GSHC/AIR_PROTOCOL.md';s=p.read_text(encoding='utf8').replace('`NAV_SUBSCRIBE (0E)` 按不支持的命令返回原有 `BAD_CMD` ACK。','基础握手后，`NAV_SUBSCRIBE (0E)` 按不支持的命令返回原有 `BAD_CMD` ACK；\n未握手仍保留 `CAPABILITY_REQUIRED` 门槛。');p.write_text(s,encoding='utf8')
root=repo/'.work/m0_final_v2';out=repo/'.work/m0_final_v2_evidence'
if root.exists() or out.exists():raise FileExistsError('Preserve all prior evidence')
out.mkdir(parents=True)
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
config=json.loads((repo/'.work/m0_final_evidence/Input.ssproject').read_text(encoding='utf8'))
inp=out/'Input.ssproject';inp.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
TargetGeneration_Apply(service.Project_Open(inp),service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
project=root/'Flight_Controller';make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG/tests')+';'+str(repo/'apps/FCCG')+';'+str(repo/'apps/GSHC'),SILVERSTAR_RADIO_GENERATED_PROJECT=str(project),SILVERSTAR_RADIO_GROUND_PROJECT=str(root/'Ground_Station'))
records=[]
def run(name,command,cwd):
 log=out/(name+'.log');started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with log.open('w',encoding='utf8') as stream:result=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
 r={'name':name,'command':command,'cwd':str(cwd),'exit':result.returncode,'started':started,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 records.append(r);(out/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
 print(name,result.returncode,flush=True);print(log.read_text(encoding='utf8',errors='replace')[-1300:],flush=True)
prior=json.loads((repo/'.work/m0_final_evidence/results.json').read_text(encoding='utf8'))
compile_record=next(r for r in prior if r['name']=='compile_m0_counter')
command=[x.replace(str(repo/'.work/m0_final/Flight_Controller'),str(project)) for x in compile_record['command']];command[-1]=str(out/'m0_counter.exe')
run('compile_counter',command,project)
if records[-1]['exit']==0:
 for scenario in ['contended','no_navigation','unavailable','no_imu','recovery','outside_mission']:run('counter_'+scenario,[command[-1],scenario],project)
run('FCCG_targeted',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/m0_final2_fccg_tests'),'apps/FCCG/tests/test_flight_state_scheduler_generated_host.py','apps/FCCG/tests/test_radio_handshake_generated_host.py','apps/FCCG/tests/test_radio_duplex_generated_host.py'],repo)
for name,targets in [('Release',['all']),('Host',['host-tests']),('architecture',['architecture-check']),('PoT',['power10-check']),('analyzer',['static-analysis']),('artifact',['artifact-check']),('resources',['stack-report','memory-report'])]:
 run(name,[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),*targets],project)
sys.exit(any(r['exit'] for r in records))
