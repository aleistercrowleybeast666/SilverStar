import json
import hashlib
import sys
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps/FCCG/src')]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.model import HardwareConfiguration
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
service=FccgService(ROOT/'apps/FCCG')
out=Path(__file__).parent
report=[]
for name,first in [('candidate_a',TargetScope.FLIGHT),('candidate_b',TargetScope.GROUND)]:
    project=out/(name+'_v4')
    if project.exists(): raise SystemExit('fresh directory required')
    model=ReferenceProject_Create('SoftwareRecovery_'+name,catalog=service.catalog)
    model.ground_target=replace(model.ground_target,enabled=True,
        board='silverstar.board.ground_station_0_5',mcu='silverstar.mcu.stm32f103c8t6',
        hardware=HardwareConfiguration(mode='board_plugin'),
        radio_plugin='silverstar.device.telemetry.sx1281',module_variant='e28_2g4m12sx',pc_interface='uart')
    model=service.ProjectConfiguration_Reconcile(model).model
    ProjectRoot_Save(model,project,create_new=True)
    reopened=service.Project_Open(project)
    assert json.dumps(reopened.Dictionary_Get(),sort_keys=True)==json.dumps(model.Dictionary_Get(),sort_keys=True)
    for scope in [first,TargetScope.ALL]:
        result=TargetGeneration_Apply(reopened,service.catalog,service.policy,project,scope,confirm_dangerous=True)
        report.append({'project':str(project),'scope':str(scope),'targets':result.targets,'files':len(result.file_hashes)})
        ProjectRoot_Save(reopened,project)
        reopened=service.Project_Open(project)
    # Regeneration must preserve user-owned first-party source.
    source=project/'Flight_Controller/Modules/Src/telemetry_service.c'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    TargetGeneration_Apply(reopened,service.catalog,service.policy,project,TargetScope.ALL,confirm_dangerous=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
(out/'generation_v4.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
