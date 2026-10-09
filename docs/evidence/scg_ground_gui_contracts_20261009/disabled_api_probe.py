"""Tiny API invariant check; disabled input must publish no firmware payload."""
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
service=FccgService(ROOT/'apps/SCG')
model=service.ReferenceProject_Create('DisabledApiInvariant')
assert not model.ground_target.enabled
model=ProjectModel_Parse(model.Dictionary_Get())
assert not model.ground_target.enabled
output=Path(__file__).resolve().parent/'disabled-api-output'
assert not output.exists()
try:
    TargetGeneration_Apply(model,service.catalog,service.policy,output,TargetScope.GROUND)
except ValueError as error:
    assert str(error)=='Ground target is disabled'
    result={'referenceEnabled':model.ground_target.enabled,'parsePreservedFalse':True,
        'groundGenerationRejected':str(error),'outputCreated':output.exists()}
else:
    raise AssertionError('Disabled Ground unexpectedly generated firmware')
assert not output.exists()
Path(__file__).with_name('disabled-api-result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result),flush=True)
