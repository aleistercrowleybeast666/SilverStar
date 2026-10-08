from pathlib import Path
import os,sys,json,time,hashlib,traceback,dataclasses
os.environ['QT_QPA_PLATFORM']='windows'
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
root=Path(__file__).resolve().parent;repo=root.parents[1]
sys.path[:0]=[str(repo/'apps/FLP/src'),str(repo/'apps/FLP')]
import numpy as np
from PySide6.QtCore import QSettings,qInstallMessageHandler,Qt
from PySide6.QtWidgets import QApplication
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.api.algorithm import ReplayRequest,ReplayMode
from silverstar_flp.log_open import LogOpenCoordinator,LogOpenRequest
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.core.project import ProjectDocument,Project_Load,ProjectResults_Load
from silverstar_flp.core.path_preferences import PathPreferences
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.ui.workers import FunctionWorker
import silverstar_flp.ui.main_window as module
from tests.test_project_artifacts import _Assert_Result
warnings=[]
def qt_message(kind,context,message):
 warnings.append({'type':int(kind),'message':message})
 with (root/'qt_messages.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(warnings[-1],ensure_ascii=False)+'\n')
 print('QT',int(kind),message,flush=True)
qInstallMessageHandler(qt_message)
app=QApplication([])
assert app.platformName()=='windows', 'Native Windows required; no offscreen fallback'
settings=QSettings(str(root/'gui_settings.ini'),QSettings.Format.IniFormat)
module.QSettings=lambda *a,**k:settings
registry=builtin_registry()
decoder=repo/'.work/bench08c_f407/KF6_Static_20261008_f045d8c.ssdecoder'
progress=[];errors=[];results=[]
def wait(w,label,timeout=120):
 deadline=time.monotonic()+timeout
 while w._active_worker is not None and time.monotonic()<deadline:
  app.processEvents();time.sleep(.01)
 assert w._active_worker is None, 'Worker timeout: '+label
 assert not errors, errors
 print('PASS',label,flush=True)
def arrays(entry):
 return {k:{n:hashlib.sha256(np.ascontiguousarray(getattr(s,n)).tobytes()).hexdigest() for n in ['timestamp_us','values','valid']} for k,s in entry.result.channels.items()}
def chart_state(w):
 return {'position':len(w.flight_page.position_plot.listDataItems()),'velocity':len(w.flight_page.velocity_plot.listDataItems()),'quaternion':len(w.flight_page.quaternion_plot.listDataItems()),'covariance':len(w.state_estimation_page.covariance_plot.listDataItems()),'nis':len(w.state_estimation_page.nis_plot.listDataItems())}
try:
 for mission in [44,45]:
  folder=root/f'p{mission}';folder.mkdir(exist_ok=False)
  w=module.MainWindow(registry,language='zh_CN',path_preferences=PathPreferences(folder/'path_prefs.json'),plugin_manager=TrustedContainerPluginManager(folder/'plugins'))
  w._log_open_coordinator=LogOpenCoordinator(registry,cache=DecoderProfileCache(folder/'cache'))
  w._Error_Show=errors.append
  w.show();app.processEvents()
  log=root/'input'/f'missions/{mission:06}/flight.sslog'
  request=LogOpenRequest(log,decoder)
  worker=FunctionWorker(lambda ctx:w._log_open_coordinator.Open(request,ctx))
  worker.is_staged_io=True
  worker.signals.progress.connect(lambda value,code:progress.append({'mission':mission,'stage':'open','value':value,'code':code}),Qt.ConnectionType.QueuedConnection)
  w._Task_Start(worker,lambda opened:w._LogOpenResult_Set(opened,ProjectDocument()),errors.append)
  wait(w,f'{mission} strict GUI open')
  assert w._log_open_result.match_mode=='exact_generation_profile'
  assert w._log_open_result.package.package_sha256=='46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2'
  ds=w._dataset
  # Actual short log, two required history runs; no ESKF15 or long-log recalculation.
  for request in [ReplayRequest(mode=ReplayMode.RECORDED_CONFIGURATION,input_source='recorded_inertial_increment'),ReplayRequest(mode=ReplayMode.WHAT_IF,input_source='corrected_imu',parameters={'gravity_mps2':9.81},process_model_revision=2)]:
   w._Replay_Start('silverstar.algorithm.kf6',request)
   wait(w,f'{mission} KF6 {request.mode.value}')
   assert len(w._replay_store.Entries_Get()) in [1,2]
  before=w._replay_store.Entries_Get()
  assert len(before)==2 and all(e.result.channels and not e.result.missing_inputs for e in before)
  assert before[0].source_id!=before[1].source_id
  # Primary recorded, secondary actual run, then reverse and save that choice.
  w._AnalysisSource_Set('recorded:kf6');w._SecondarySource_Set(before[0].source_id)
  native_recorded=chart_state(w)
  assert native_recorded['position']==6 and native_recorded['velocity']==6
  w._AnalysisSource_Set(before[0].source_id);w._SecondarySource_Set('recorded:kf6')
  native_recomputed=chart_state(w)
  assert native_recomputed['position']==6 and native_recomputed['velocity']==6
  expected_primary=w._replay_store.ActiveSource_Get().source_id
  expected_secondary=w._secondary_source_id
  before_hash={e.result_id:arrays(e) for e in before}
  project=folder/f'mission{mission}.ssflp'
  assert w._Project_Write(project,background=True,save_data=True)
  worker=w._active_worker
  worker.signals.progress.connect(lambda value,code:progress.append({'mission':mission,'stage':'save','value':value,'code':code}),Qt.ConnectionType.QueuedConnection)
  wait(w,f'{mission} actual artifact save')
  assert project.is_file() and not w._project_dirty
  loaded=Project_Load(project);restored=ProjectResults_Load(loaded).Entries_Get()
  assert len(restored)==2
  for a,b in zip(before,restored):
   assert (a.result_id,a.source_id,a.run_index)==(b.result_id,b.source_id,b.run_index)
   _Assert_Result(a.result,b.result)
  assert {e.result_id:arrays(e) for e in restored}==before_hash
  assert loaded.ui_state['analysis_source']==expected_primary and loaded.ui_state['secondary_source']==expected_secondary
  # Real GUI project restore from saved artifacts; prohibit recomputation on reopen.
  original=type(registry.Algorithm_Get('silverstar.algorithm.kf6')).run
  type(registry.Algorithm_Get('silverstar.algorithm.kf6')).run=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Unexpected recompute on reopen'))
  try:
   w._Project_Open(project);wait(w,f'{mission} strict GUI reopen')
  finally:type(registry.Algorithm_Get('silverstar.algorithm.kf6')).run=original
  after=w._replay_store.Entries_Get()
  assert len(after)==2 and {e.result_id:arrays(e) for e in after}==before_hash
  assert not w._project.restoration_issues
  assert w._replay_store.ActiveSource_Get().source_id==expected_primary and w._secondary_source_id==expected_secondary
  assert chart_state(w)==native_recomputed
  for page,name in [(0,'overview'),(2,'flight'),(3,'estimation')]:
   w.navigation_list.setCurrentRow(page);app.processEvents();time.sleep(.15);app.processEvents()
   assert w.grab().save(str(folder/(name+'.png')))
  samples=[]
  for key in ['IMU_CORRECTED','INERTIAL_INCREMENT','ESTIMATOR_STEP','ESTIMATOR','TELEMETRY_DIAG','STATS']:
   records=ds.records.get(key,())
   dt=np.diff([r.timestamp_us for r in records])
   numeric={}
   for field in records[0].payload if records else []:
    values=[r.payload[field] for r in records]
    if all(isinstance(v,(int,float)) for v in values):numeric[field]={'min':min(values),'max':max(values),'first':values[0],'last':values[-1]}
   samples.append({'record_type':key,'count':len(records),'max_interval_us':int(dt.max()) if len(dt) else None,'first':records[0].timestamp_us if records else None,'last':records[-1].timestamp_us if records else None,'fields':numeric})
  record={'mission':mission,'project':str(project),'run_count':len(after),'run_ids':[e.result_id for e in after],'primary':expected_primary,'secondary':expected_secondary,'chart_state':native_recomputed,'run_arrays_sha256':before_hash,'run_modes':[e.mode.value for e in after],'run_fidelity':[e.result.fidelity.value for e in after],'record_audit':samples,'progress_count':len(progress),'platform':app.platformName(),'errors':list(errors)}
  (folder/'gui_result.json').write_text(json.dumps(record,indent=2,default=str),encoding='utf-8')
  results.append(record)
  w._Project_SetDirty(False);w.import_dialog.reject();w.export_dialog.reject();w.close();app.processEvents()
 print('PASS native same-process actual mission 44/45 GUI roundtrip',flush=True)
except BaseException as exc:
 (root/'gui_failure.json').write_text(json.dumps({'error':repr(exc),'traceback':traceback.format_exc(),'completed':results},indent=2,default=str),encoding='utf-8')
 raise
finally:
 (root/'gui_progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8')
 (root/'qt_messages.json').write_text(json.dumps(warnings,indent=2,ensure_ascii=False),encoding='utf-8')
