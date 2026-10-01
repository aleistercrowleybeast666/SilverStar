import pathlib, sys, json, time, hashlib
root=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'apps/FCCG/src'),str(root/'apps/FCCG/tests')]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from test_gui_qa_repair import _GroundF103Model_Get
service=FccgService(root/'apps/FCCG')
model=_GroundF103Model_Get(service.catalog)
model.identity=type(model.identity)('SCG_Closeout_KF6_v1')
output=root/'.work/SCG_Closeout_2175d95_v3'
if output.exists():
    raise SystemExit('Independent validation output already exists; select a new version')
start=time.perf_counter()
ProjectRoot_Save(model,output,create_new=True)
result=TargetGeneration_Apply(model,service.catalog,service.policy,output,TargetScope.ALL,confirm_dangerous=True)
evidence=root/'docs/FCCG/gui_closeout_20261001_v1'
(evidence/'input_configuration.ssproject').write_text(json.dumps(model.Dictionary_Get(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(output=str(output),targets=result.targets,seconds=time.perf_counter()-start,
    file_count=len(result.file_hashes)),indent=2))
