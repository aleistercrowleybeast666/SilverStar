from pathlib import Path
from dataclasses import replace
import sys,json,hashlib,subprocess,datetime
repo=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
scg=repo/'apps/SCG'
sys.path.insert(0,str(scg/'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
from silverstar_fccg.project.model import ProjectModel_Load
source=repo/'.work/Q2F407_7fa06c4'
target=repo/'.work/bench08b_f407'
descriptor=source/'SilverStar.ssproject'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo).strip()
assert subprocess.check_output(['git','branch','--show-current'],cwd=repo).decode().strip()=='fix/nightly-user-ready-20261003'
assert sha(descriptor)=='92fa295afa7c97325f85a5be9fef6756b84393355b5a5e16604949cafb5333d6'
if target.exists():raise SystemExit('Refuse overwrite of any existing project')
raw=json.loads(descriptor.read_text(encoding='utf-8'))
model=ProjectModel_Load(descriptor)
assert model.mcu=='silverstar.mcu.stm32f407vet6' and model.board=='silverstar.board.silverstar_0_5'
assert model.strategies['estimator']=='silverstar.algorithm.estimator.kf6'
assert raw['modes']['calibration']==['OneFace'] and raw['modes']['deployment']==['Delay']
assert raw['mode_parameters']['deployment']['Delay']['delay']==10.0
assert model.build.feature_tier=='full'
service=FccgService(scg)
current=service.catalog.Component_Get(model.mcu).ManifestSha256_Get()
old=model.hardware.platform_manifest_sha256
if current!=old:
    previous=repo/'.work/kf6_stage2_candidate/apps/SCG/plugins/builtin/silverstar_mcu_stm32f407vet6/plugin.json'
    assert json.loads(previous.read_text(encoding='utf-8'))==json.loads((scg/'plugins/builtin/silverstar_mcu_stm32f407vet6/plugin.json').read_text(encoding='utf-8')), 'Platform changed semantically; refuse automatic lock update'
    model.hardware=replace(model.hardware,platform_manifest_sha256=current)
model.identity=replace(model.identity,name='KF6_Static_20261008_'+head[:7])
assembler=ProjectAssembler(service.policy,service.catalog,WorkspacePolicy(target))
plan=assembler.Plan(model,target/'Flight_Controller')
record={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_head':head,'source_descriptor':str(descriptor),'source_descriptor_sha256':sha(descriptor),'target':str(target),'platform_lock_before':old,'platform_lock_current':current,'model_feature_tier':model.build.feature_tier,'plan_valid':plan.valid,'dangerous':plan.dangerous,'validation':str(plan.validation),'configuration_changes':'New display name; schema migration/default full tier; equal-parsed MCU lock only if required. Preserve devices/resources, ORIENT, calibration/alignment, mathematical parameters, Delay10 and queue policy.'}
(out/'generation_b_plan.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2),flush=True)
if not plan.valid or plan.dangerous:raise SystemExit('Invalid/dangerous plan; no generation')
if '--apply' not in sys.argv:raise SystemExit(0)
result=TargetGeneration_Apply(model,service.catalog,service.policy,target,TargetScope.FLIGHT)
new=json.loads((target/'SilverStar.ssproject').read_text(encoding='utf-8'))
oldsem=json.loads((source/'Flight_Controller/Generated/project_semantics.json').read_text(encoding='utf-8'))
newsem=json.loads((target/'Flight_Controller/Generated/project_semantics.json').read_text(encoding='utf-8'))
assert oldsem['resource_assignments']==newsem['resource_assignments'],'Resource assignments changed'
for key in ['components','modes','alignment','mode_parameters','algorithm_parameters','air_link','flight_tx_power_dbm','resources','capability_sources']:
    assert raw[key]==new[key], 'Hardware/navigation configuration changed: '+key
assert sha(descriptor)==record['source_descriptor_sha256']
compare={}
for n in ['Core/Src/main.c','Core/Inc/main.h','Flight_Controller0.5.ioc','APP/Inc/app_task_config.h']:
    a=source/'Flight_Controller'/n;b=target/'Flight_Controller'/n
    compare[n]={'old_sha256':sha(a),'new_sha256':sha(b),'identical':a.read_bytes()==b.read_bytes()}
record.update(generated=True,resources_unchanged=True,configuration_keys_unchanged=True,files=compare,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'generation_b_result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2),flush=True)
