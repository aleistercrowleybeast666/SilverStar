from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib,shutil
TASK=Path(__file__).parent
sys.path.insert(0,str(TASK/'r/apps/SCG/src'))
from resume_scg_d_final import environment,CODE,room,git
import os
os.environ.update(environment())
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.usb_ground_flow import UsbGroundQuality_Run,UsbGroundRefresh_Inspect
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.task import TaskContext
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.quality_results import QualityResult_Save
from silverstar_fccg.build.runner import BuildAction
assert git('rev-parse','HEAD')==CODE and not git('status','--porcelain')
room()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
catalog=PluginCatalog(TASK/'r/apps/SCG/plugins/builtin',TASK/'r/apps/SCG/plugins/installed');catalog.Scan()
archive=TASK/'ds-migration-quality';archive.mkdir(exist_ok=True)
records=[]
for row in map(json.loads,(TASK/'ds-migrated-build-index.jsonl').read_text().splitlines()):
 output=Path(row['output']);project=Path(row['project_root']);part=row['part']
 qpath=output/'.fccg/quality-results.json'
 original=archive/(part+'-original-quality.json');assert not original.exists();shutil.copyfile(qpath,original)
 immutable=[output/x for x in ['receipt.json','backend-receipt.json','build/native.elf','build/analysis/native.elf']]+[project/'SilverStar.ssproject']
 before={str(p):sha(p) for p in immutable}
 service_root=Path(os.environ['TEMP'])/('quality-'+part);service_root.mkdir()
 service=FccgService(service_root);service.catalog=catalog;service.assembler.catalog=catalog
 receipt=json.loads((output/'receipt.json').read_text());cache=Path(receipt['snapshot_root']).parent.parent
 service.hardware_importer.cache_root=cache;service.hardware_importer.policy=WorkspacePolicy(cache.parent)
 model=ProjectModel_Load(project/'SilverStar.ssproject')
 for action in [BuildAction.ARCHITECTURE_CHECK,BuildAction.ARTIFACT_CHECK]:
  lines=[];outcome=UsbGroundQuality_Run(service,model,project,action,TaskContext(line_callback=lines.append))
  assert outcome.result is not None and outcome.succeeded,(outcome.error,lines)
  result=outcome.result
  saved=QualityResult_Save(output,task=action.value,succeeded=outcome.succeeded,duration=outcome.duration,summary='Migration normal check: '+result.output.strip().splitlines()[-1],input_sha256=outcome.input_sha256,command=result.command,details=result.output)
  records.append({'part':part,'action':action.value,'exit':result.return_code,'command':result.command,'duration':outcome.duration,'input_sha256':outcome.input_sha256,'output':result.output,'new_timestamp':saved.timestamp})
  print(part,action.value,result.return_code,flush=True)
 refreshed=UsbGroundRefresh_Inspect(service,model,project,TaskContext())
 assert not refreshed.error and refreshed.states=={} and len(refreshed.records)==2,refreshed
 assert before=={str(p):sha(p) for p in immutable}
 shutil.copyfile(qpath,archive/(part+'-fresh-quality.json'))
 records.append({'part':part,'original_quality_sha256':sha(original),'fresh_quality_sha256':sha(qpath),'immutable_sha256':before,'states':refreshed.states})
(TASK/'ds-migration-quality.json').write_text(json.dumps({'source_commit':CODE,'recorded_utc':datetime.now(timezone.utc).isoformat(),'scope':'Original pointer-dependent quality digests correctly stale after migration. Original records retained. Actual original architecture and artifact product APIs rerun and QualityResult_Save writes fresh normal results. Model/receipts/ELFs unchanged. No digest replacement or stale guard relaxation.','records':records},indent=2))
