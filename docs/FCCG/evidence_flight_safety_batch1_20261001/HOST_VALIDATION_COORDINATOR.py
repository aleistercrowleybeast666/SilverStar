from pathlib import Path
import ctypes,datetime,hashlib,json,os,re,shlex,subprocess,sys,time
if os.name=='nt':ctypes.windll.kernel32.SetErrorMode(0x0001|0x0002|0x8000)
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'apps/FCCG/src'))
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True)==''
o=r/'.work/day_flight1_host_final';o.mkdir(exist_ok=True)
dest=r/'.work'/('FlightSafety_'+head[:7])/'ExistingHardware'
assert not dest.exists(),dest
source=Path(r'D:\stm32_project\SS_0_5_TEST_4_versions\FinalCandidate_ddb73bb_20261001\ExistingHardware\SilverStar.ssproject')
catalog=PluginCatalog(r/'apps/FCCG/plugins/builtin',r/'apps/FCCG/plugins/installed');catalog.Scan()
model=ProjectModel_Load(source)
result=TargetGeneration_Apply(model,catalog,WorkspacePolicy(r/'apps/FCCG'),dest,TargetScope.ALL)
make='D:/msys64/ucrt64/bin/mingw32-make.exe';arm=Path('D:/Arm GNU Toolchain/14.3 rel1/bin');env=os.environ.copy();env['PATH']=str(arm)+';D:/msys64/ucrt64/bin;'+env['PATH']
ground=dest/'Ground_Station';flight=dest/'Flight_Controller';results=[]
record={'source_commit':head,'directory':str(dest),'source_configuration':str(source),'generation':'fresh ALL via TargetGeneration_Apply, existing hardware route; no prior ELF','timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'arm_version':subprocess.check_output([str(arm/'arm-none-eabi-gcc.exe'),'--version'],text=True),'host_version':subprocess.check_output(['D:/msys64/ucrt64/bin/gcc.exe','--version'],text=True),'results':results}
def save(): (o/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
def run(name,command,cwd,timeout=900):
    print('BEGIN',name,flush=True);log=o/(name+'.log');start=time.monotonic()
    with log.open('w',encoding='utf-8') as f:
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
        record['running']={'name':name,'pid':process.pid,'log':str(log)};save()
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate();code=process.wait(timeout=15);raise
    entry={'name':name,'command':command,'directory':str(cwd),'exit_code':code,'seconds':time.monotonic()-start,'log':str(log)}
    results.append(entry);record.pop('running',None);save();print('DONE',name,code,flush=True)
    return code
save()
assert not list(dest.rglob('*.elf'))
previous=json.loads((r/'.work/day_flight1_final/result.json').read_text(encoding='utf-8'))
old=Path(previous['directory']);comparisons=[]
for target in ('Flight_Controller','Ground_Station'):
    for p in (dest/target).rglob('*'):
        if not p.is_file() or 'Tests' in p.relative_to(dest/target).parts:continue
        if p.suffix.lower() not in ('.c','.h','.s','.ld','.mk','.ssdecoder') and p.name!='Makefile':continue
        before=old/target/p.relative_to(dest/target)
        same=before.is_file() and before.read_bytes()==p.read_bytes()
        comparisons.append({'file':str(p.relative_to(dest)),'identical_to_firmware_95abac8':same,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
record['firmware_source_commit']='95abac8c06535e144e0e91f3dfafaaf02a4bd782'
record['test_commit']=head
record['previous_firmware_evidence']=str(r/'.work/day_flight1_final/result.json')
record['firmware_equivalence']=comparisons
assert all(c['identical_to_firmware_95abac8'] for c in comparisons),[c for c in comparisons if not c['identical_to_firmware_95abac8']]
save()
run('flight_host',[make,'CONFIG=Release','HOST_CC=D:/msys64/ucrt64/bin/gcc.exe','host-tests'],flight)
run('flight_power10',[make,'CONFIG=Release','power10-check'],flight)
run('ground_power10',[make,'power10-check'],ground)
record['artifacts']=[];record['sizes']={}
for root in (ground,flight):
    for suffix in ('*.elf','*.map','*.bin','*.hex','*.ssdecoder'):
        for p in root.rglob(suffix):record['artifacts'].append({'file':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    for p in root.rglob('*.elf'):
        record['sizes'][root.name]=subprocess.check_output([str(arm/'arm-none-eabi-size.exe'),'-A',str(p)],text=True)
record['configuration_sha256']=hashlib.sha256((dest/'SilverStar.ssproject').read_bytes()).hexdigest()
record['source_files_sha256']={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [r/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Src/system_navigation_health.c',r/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Common/Src/common_spsc_queue.c']}
save()
(dest.parent/'FLIGHT_BATCH1_HOST_MANIFEST.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print('COMPLETE',head,dest,flush=True)
