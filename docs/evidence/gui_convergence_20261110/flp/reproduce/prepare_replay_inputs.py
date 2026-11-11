"""Separate mode1 replay fixtures from the independently tested mode0 projects."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys

TASK=Path(__file__).resolve().parent
ROOT=TASK.parents[2]
sys.path.insert(0,str(ROOT/'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.render import LogDecoderProfile_Render
from silverstar_fccg.project.validation import Project_Validate

service=FccgService(ROOT/'apps/SCG')
service.policy=WorkspacePolicy(TASK/'inputs')
receipts={}
for name in ('existing','imported','eskf'):
    saved=service.Project_Open(TASK/'inputs'/name)
    model=service.ReferenceProject_Create(saved.identity.name)
    model.strategies=saved.strategies
    model.algorithm_parameters=saved.algorithm_parameters
    model.board=saved.board
    model.hardware=saved.hardware
    model.resource_assignments=saved.resource_assignments
    model.logging_streams=saved.logging_streams
    model=service.ProjectConfiguration_Reconcile(model).model
    model.algorithm_parameters[model.strategies['estimator']]['fusion_timing_mode']=1
    validation=Project_Validate(model,service.catalog)
    assert validation.valid, validation.errors
    package=LogDecoderProfile_Render(model,service.catalog)
    output=TASK/'inputs'/('aggregation-'+name)
    output.mkdir(exist_ok=False)
    path=output/(model.identity.name+'.ssdecoder')
    path.write_bytes(package.content)
    receipts[name]=dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),
                        mode=1,source_project=str(TASK/'inputs'/name))
    if name=='eskf':
        project=TASK/'inputs/eskf-replay'
        service.Project_Save(model,project,confirm_dangerous=True)
        receipts['eskf-replay']=str(project)
model=service.ReferenceProject_Create('SS_TEST_0')
service.Project_Save(model,TASK/'inputs/codec-golden',confirm_dangerous=True)
receipts['codec-golden']=str(TASK/'inputs/codec-golden')
(TASK/'inputs/replay-projects.json').write_text(json.dumps(receipts,indent=2),encoding='utf8')
print('replay and current codec projects generated',flush=True)
