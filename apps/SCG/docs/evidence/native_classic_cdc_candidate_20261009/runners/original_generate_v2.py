"""Actual official import and fresh generation with private byte-copy cache."""
from pathlib import Path
from dataclasses import replace
import hashlib,json,os,sys
BASE=Path('D:/python_software/SilverStar'); REPO=BASE/'.work/qint';SCG=REPO/'apps/SCG'
ORIGIN=Path('C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation')
OUT=Path('C:/Users/chdxm/AppData/Local/Temp/ssgroundint9e')
if OUT.exists():raise RuntimeError('Fresh output exists')
OUT.mkdir();WORK=OUT/'workspace';WORK.mkdir()
sys.path[:0]=[str(SCG/'src'),str(SCG/'tests')]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
from test_round2_targets import _GroundBoardProject_Get
cache=ORIGIN/'workspace/.fccg/hardware_imports'
ids=set(ProjectModel_Load(ORIGIN/'dep9'/('generated-'+case)/'SilverStar.ssproject').ground_target.hardware.snapshot_id for case in ('f103-usb','f103-uart','f407-usb'))
hashes={}
for ident in ids:
 for p in (cache/ident).rglob('*'):
  if p.is_file():
   dest=WORK/'.fccg/hardware_imports'/ident/p.relative_to(cache/ident);dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(p.read_bytes());hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
class CachedOnlyImporter(CubeMxImporter):
 def _Snapshot_Store(self,root,files,digest,**kwargs):
  expected=self.cache_root/digest/'STM32CubeMX'
  if not expected.is_dir():raise RuntimeError('Uncached input; stopped before copying: '+digest)
  return super()._Snapshot_Store(root,files,digest,**kwargs)
service=FccgService(WORK);catalog=PluginCatalog(SCG/'plugins/builtin',SCG/'plugins/installed');catalog.Scan();service.catalog=catalog
service.hardware_importer=CachedOnlyImporter(service.policy)
results=[]
for name,mcu,pc in (('f103-usb','stm32f103c8t6','usb_cdc'),('f103-uart','stm32f103c8t6','uart'),('f407-usb','stm32f407vet6','usb_cdc')):
 model=_GroundBoardProject_Get(catalog);cube=ORIGIN/('cube-'+name)
 imported=service.CubeMxProject_Import(cube,model,risk_acknowledged=True,target='ground')
 hw=imported.hardware; resources={r.resource_id:r for r in hw.resources}
 nss='SPI_RADIO_NSS' if 'SPI_RADIO_NSS' in resources else 'RADIO_NSS'
 assignments={'radio0:radio_bus':'SPI1','radio0:radio_nss':nss,'radio0:radio_reset':'RADIO_RST','radio0:radio_busy':'RADIO_BUSY','radio0:radio_dio1':'RADIO_DIO1','radio0:time':'SYSTEM_TIME'}
 exact=catalog.Component_Get('silverstar.mcu.'+mcu)
 model.ground_target=replace(model.ground_target,board='',mcu=exact.component_id,hardware=hw,pc_interface=pc,pc_resource='USART1' if pc=='uart' else '',resource_assignments=assignments,baudrate=resources['USART1'].metadata['baud_rate'],build=replace(model.ground_target.build,target_profile=exact.platform.build_target_profile))
 output=OUT/name;ProjectRoot_Save(model,output,create_new=True)
 result=TargetGeneration_Apply(model,catalog,service.policy,output,TargetScope.ALL if name=='f103-usb' else TargetScope.GROUND)
 results.append({'case':name,'output':str(output),'snapshot_id':hw.snapshot_id,'configuration':model.Dictionary_Get(),'file_hashes':result.file_hashes})
 print('Imported and generated',name,len(result.file_hashes),flush=True)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
(OUT/'generation.json').write_text(json.dumps({'cases':results,'cached_original_hashes':hashes,'source_commit':'56448bd35736221d7885a26704f2f953b0fe5055','cache_file_count':len(hashes)},indent=2),encoding='utf8')
print('Original cache hashes verified; private cache byte copies',len(hashes),flush=True)


