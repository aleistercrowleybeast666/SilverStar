from pathlib import Path
import sys,json,hashlib,subprocess,datetime,runpy,re

repo=Path.cwd();out=Path(__file__).resolve().parent
sys.path.insert(0,str(repo/'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
from silverstar_fccg.project.model import ProjectModel_Load

source=repo/'.work/bench08c_f407';target=out/'project'
assert not target.exists(),'Preserve any existing candidate'
descriptor=source/'SilverStar.ssproject';original=descriptor.read_bytes()
model=ProjectModel_Load(descriptor);raw=json.loads(original)
assert model.mcu=='silverstar.mcu.stm32f407vet6' and model.build.feature_tier=='full'
assert model.strategies['estimator']=='silverstar.algorithm.estimator.kf6'
assert raw['modes']=={'calibration':['OneFace'],'deployment':['Delay']}
assert raw['mode_parameters']['deployment']['Delay']['delay']==10.0
service=FccgService(repo/'apps/SCG')
assembler=ProjectAssembler(service.policy,service.catalog,WorkspacePolicy(target))
plan=assembler.Plan(model,target/'Flight_Controller')
record={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'base_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_descriptor':str(descriptor),'source_descriptor_sha256':hashlib.sha256(original).hexdigest(),
        'target':str(target),'plan_valid':plan.valid,'plan_dangerous':plan.dangerous,
        'validation':str(plan.validation),'configuration_changes':'None; isolated fresh project retains previously approved display label, all devices/resources/math/tier/queue/stack/RF/Delay10/OneFace. Source revision/dirty hash is recorded separately.'}
(out/'source_diff.patch').write_bytes(subprocess.check_output(['git','diff','--binary','--','apps/SCG']))
record['dirty_patch_sha256']=hashlib.sha256((out/'source_diff.patch').read_bytes()).hexdigest()
(out/'generation_plan.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
assert plan.valid and not plan.dangerous,'Invalid/dangerous fresh generation'
TargetGeneration_Apply(model,service.catalog,service.policy,target,TargetScope.FLIGHT)
new=json.loads((target/'SilverStar.ssproject').read_text(encoding='utf-8'))
for key in ['components','modes','alignment','mode_parameters','algorithm_parameters','air_link','flight_tx_power_dbm','resources','capability_sources']:
    assert raw[key]==new[key],key
assert descriptor.read_bytes()==original
owner=repo/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload'
generated=target/'Flight_Controller';mapping={}
for name in ['APP/Src/estimator_task.c','APP/Src/logger_bus.c','APP/Src/flight_task.c','Tools/check_task_stacks.py','Tools/check_power_of_ten.ps1']:
    a=owner/name;b=generated/name
    assert a.read_bytes()==b.read_bytes(),name
    mapping[name]=hashlib.sha256(a.read_bytes()).hexdigest()
for name in ['APP/Inc/app_task_config.h','System/User/system_user_config.h','Core/Src/main.c','Core/Inc/main.h','Flight_Controller0.5.ioc']:
    assert (source/'Flight_Controller'/name).read_bytes()==(generated/name).read_bytes(),name
checker=runpy.run_path(str(generated/'Tools/check_task_stacks.py'))
source_list=(generated/'Generated/project_sources.mk').read_text(encoding='utf-8')
block=re.search(r'(?ms)^C_SOURCES \+= \\\n(.*?)(?:\n\n|\Z)',source_list)
assert block
sources=[x.strip().removesuffix('\\').strip() for x in block[1].splitlines()]
unknown=[]
for name in sources:
    actual=checker['BindingSourceHash_Get']((generated/name).read_text(encoding='utf-8'))
    if actual not in checker['BindingSourceVersions_Get'](name):unknown.append({'path':name,'normalized_source_sha256':actual})
record.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),generated=True,
              configuration_keys_unchanged=True,queue_stack_user_config_and_hardware_files_identical=True,
              owner_generated_hashes=mapping,compiled_sources=len(sources),unknown_stack_source_bindings=unknown,
              allowlist_updated=False)
(out/'generation_result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2),flush=True)
