import os,sys,json,subprocess,hashlib,traceback
from pathlib import Path
from dataclasses import replace
root=Path(r'D:\python_software\SilverStar\.work\GuiFieldBlockers_20261002')
out=Path(__file__).parent/('build_evidence_'+sys.argv[1] if len(sys.argv)>1 else 'build_evidence');out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'apps/FCCG/src'))
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
from silverstar_fccg.core.workspace import WorkspacePolicy
app=QApplication([])
w=MainWindow(SettingsStore(root/'apps/FCCG/.work/build_evidence/settings.ini'),service=FccgService(root/'apps/FCCG'))
errors=[];w._Error_Show=lambda e:errors.append(str(e))
w._BoardSelection_Change('silverstar.board.silverstar_0_5')
w._GroundBoard_Change('silverstar.board.ground_station_0_5')
w._GroundTarget_Change('enabled',True)
w._GroundTarget_Change('radio_plugin','silverstar.device.telemetry.sx1281')
w._GroundTarget_Change('pc_interface','uart')
model=w._model
project=root/('.work/FieldBuild_20261002_'+sys.argv[1] if len(sys.argv)>1 else '.work/FieldBuild_20261002')
commit=subprocess.check_output(['git','-c',f'safe.directory={root.as_posix()}','rev-parse','HEAD'],cwd=root,text=True).strip()
summary={'source_commit':commit,'errors':errors,'memory_layout':model.build.memory_layout,'ground_module':model.ground_target.module_variant,'pc_resource':model.ground_target.pc_resource,'commands':[]}
try:
 w._service.ProjectRoot_Save(model,project,create_new=True)
 w._Project_Open(project)
 assert w._model.ground_target==model.ground_target
 result=TargetGeneration_Apply(w._model,w._service.catalog,WorkspacePolicy(project),project,TargetScope.ALL,confirm_dangerous=True)
 summary['generated_targets']=result.targets
 w.close()
 env=os.environ.copy();env['PATH']=r'D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+env['PATH']
 for target in result.targets:
  cmd=[r'D:\msys64\ucrt64\bin\mingw32-make.exe','-j2','all','CONFIG=Release']
  with (out/(target+'.log')).open('w',encoding='utf8') as log:
   r=subprocess.run(cmd,cwd=project/target,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
  summary['commands'].append({'cwd':str(project/target),'command':cmd,'exit':r.returncode})
  print(target,'exit',r.returncode,flush=True)
 summary['artifacts']={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*.elf')}
except Exception as e:
 summary['failure']=str(e);traceback.print_exc()
(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps(summary),flush=True)
