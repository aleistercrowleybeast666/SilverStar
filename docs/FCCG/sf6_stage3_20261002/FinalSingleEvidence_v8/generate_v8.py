import sys, json, hashlib, copy
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
service=FccgService(ROOT/'apps/FCCG')
source=Path(r'D:\stm32_project\SS_0_5_TEST_4')
model=service.Project_Open(source)
print('real configuration',model.strategies, flush=True)
report=[]
for name,algorithm in [('PureINS',None),('KF6','silverstar.algorithm.estimator.kf6'),
                       ('ESKF15','silverstar.algorithm.estimator.eskf15'),('SF6','silverstar.algorithm.estimator.sf6')]:
    project=Path(__file__).parent/(name+'_v8')
    if project.exists(): raise SystemExit('Fresh directory required: '+str(project))
    candidate=copy.deepcopy(model)
    candidate.strategies=dict(model.strategies,estimator=algorithm)
    candidate.modes["deployment"]=["Delay"]
    candidate.mode_parameters["deployment"]["Delay"]["delay"]=10.0
    candidate=service.ProjectConfiguration_Reconcile(candidate).model
    ProjectRoot_Save(candidate, project, create_new=True)
    candidate=service.Project_Open(project)
    result=TargetGeneration_Apply(candidate,service.catalog,service.policy,project,
                                 TargetScope.FLIGHT,confirm_dangerous=True)
    ProjectRoot_Save(candidate,project)
    reopened=service.Project_Open(project)
    assert reopened.Dictionary_Get()==candidate.Dictionary_Get()
    report.append(dict(name=name,project=str(project),algorithm=algorithm,
                       files=len(result.file_hashes),configuration=reopened.Dictionary_Get()))
    print('generated '+name,flush=True)
(Path(__file__).parent/'generation_v8.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
