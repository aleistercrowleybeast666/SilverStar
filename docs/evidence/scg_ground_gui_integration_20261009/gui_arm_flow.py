"""Isolated offscreen GUI flow using reused official CubeMX validation roots."""
from dataclasses import replace, asdict
from pathlib import Path
import hashlib, json, os, shutil, sys, time

REPO=Path(__file__).resolve().parents[2]
EVIDENCE=Path(__file__).resolve().parent
VALIDATION=Path('C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation')
sys.path[:0]=[str(REPO/'apps/SCG/src')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildRunner
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.ui.main_window import MainWindow

app=QApplication([])
service=FccgService(VALIDATION/'workspace')
service.catalog=PluginCatalog(REPO/'apps/SCG/plugins/builtin',REPO/'apps/SCG/plugins/installed')
service.catalog.Scan()
window=MainWindow(SettingsStore(VALIDATION/'workspace/gui-integration-20261009/gui.ini'),service=service)
errors=[]
window._Error_Show=lambda *args:errors.append([str(arg) for arg in args])
window._MessageBox_Exec=lambda *args,**kwargs:QMessageBox.StandardButton.Discard
window._model=service.Project_Open(VALIDATION/'generated-f103-usb')
window._Project_Refresh()
events=[]
original_progress=window._Task_Progress
def progress(value,code):
    events.append({'value':value,'workerActive':window._active_worker is not None,'code':code})
    original_progress(value,code)
window._Task_Progress=progress
builds=[]
original_run=BuildRunner.Target_Run
def target_run(self,*args,**kwargs):
    result=original_run(self,*args,**kwargs)
    builds.append(result)
    (EVIDENCE/'arm-build.log').write_text(result.output,encoding='utf8')
    return result
BuildRunner.Target_Run=target_run
def wait():
    deadline=time.monotonic()+90
    while window._active_worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    app.processEvents()
    assert window._active_worker is None,'bounded GUI worker timeout'

cube=VALIDATION/'cube-f103-usb'
QFileDialog.getExistingDirectory=lambda *args:str(cube)
before_snapshots=sorted(str(p) for p in service.hardware_importer.cache_root.glob('*/STM32CubeMX'))
window._GroundCubeMxImport_Request(True)
wait()
assert not errors,[e[0] for e in errors]
ground=window._model.ground_target
assert ground.hardware.hal_cmsis_source_policy=='imported_tree_authoritative'
resources={r.resource_id:r for r in ground.hardware.resources}
assignments={'radio0:radio_bus':'SPI1','radio0:radio_nss':'SPI_RADIO_NSS' if 'SPI_RADIO_NSS' in resources else 'RADIO_NSS',
    'radio0:radio_reset':'RADIO_RST','radio0:radio_busy':'RADIO_BUSY',
    'radio0:radio_dio1':'RADIO_DIO1','radio0:time':'SYSTEM_TIME'}
window._model.ground_target=replace(ground,pc_interface='usb_cdc',pc_resource='',activity_led_enabled=False,
    resource_assignments=assignments,build=replace(ground.build,make_command=shutil.which('mingw32-make'),
        gcc_path=shutil.which('arm-none-eabi-gcc'),tool_paths={}))
window._Project_Refresh()
assert not GroundTargetIssues_Get(window._model,service.catalog)
only=EVIDENCE/'ioc_only'
only.mkdir(exist_ok=True)
(only/'test.ioc').write_bytes(next(cube.glob('*.ioc')).read_bytes())
QFileDialog.getExistingDirectory=lambda *args:str(only)
old=asdict(window._model.ground_target)
window._GroundCubeMxImport_Request(True)
wait()
assert errors and asdict(window._model.ground_target)==old
rejection=errors[:]
errors.clear()
window._project_root=VALIDATION/'generated-f103-usb'
window._Targets_Generate('generate_ground')
wait()
assert not errors,errors
generation_state=window.progress_bar.property('taskState')
assert generation_state=='success'
# Regeneration preserves identical files. Request one fresh compilation in this
# disposable reused target by touching only a generated first-party source.
owned_source=window._project_root/'Ground_Station/Generated/Src/pc_byte_stream.c'
owned_hash=hashlib.sha256(owned_source.read_bytes()).hexdigest()
os.utime(owned_source,None)
assert hashlib.sha256(owned_source.read_bytes()).hexdigest()==owned_hash
events.clear()
window._TargetAction_Request('ground_build')
wait()
assert not errors,errors
assert builds and builds[-1].succeeded and builds[-1].plan.compile_steps>0
assert builds[-1].completed_steps==builds[-1].plan.total_steps
assert any(0<e['value']<.99 and e['workerActive'] for e in events)
assert window.progress_bar.value()==1000 and window.progress_bar.property('taskState')=='success'
target=window._project_root/'Ground_Station'
(EVIDENCE/'arm-build.log').write_text(builds[-1].output,encoding='utf8')
files=['build/ground.elf','build/ground.bin','build/ground.map','Generated/ground_source_graph.json']
summary={'status':'GUI flow passed; USB candidate pending independent backend corrections',
    'reusedValidationRoot':str(VALIDATION),'importedSnapshot':ground.hardware.snapshot_id,
    'iocOnlyRejection':rejection,'generationState':generation_state,
    'buildCommand':builds[-1].command,'returnCode':builds[-1].return_code,
    'incrementalCompileTrigger':'timestamp only: Generated/Src/pc_byte_stream.c; content unchanged',
    'triggerSourceSha256':owned_hash,
    'plan':asdict(builds[-1].plan),'completedSteps':builds[-1].completed_steps,'guiEvents':events,
    'artifactHashes':{f:hashlib.sha256((target/f).read_bytes()).hexdigest() for f in files},
    'snapshotsBefore':before_snapshots,
    'snapshotsAfter':sorted(str(p) for p in service.hardware_importer.cache_root.glob('*/STM32CubeMX')),
    'hardware':'NOT EXECUTED','criticalContractReview':'NOT PROVEN'}
(EVIDENCE/'gui-arm-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in summary.items() if k!='guiEvents'},indent=2),flush=True)
window.close()
app.processEvents()
