"""Small-budget adversarial inputs; never allocate a large array or run long replay."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import gzip
import json
import stat

import numpy as np
import pytest

from silverstar_flp.core import artifacts
from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.context import TaskContext, TaskCancelledError
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load
from silverstar_flp.core.replay_execution import Replay_Execute
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_project_artifacts import _Document_Build


def _SmallRun(tmp_path, algorithm='silverstar.algorithm.pure_ins'):
    opened = NavigationPair_Open(tmp_path/'pair', flight_samples=21)
    plugin = builtin_registry().Algorithm_Get(algorithm)
    request = ReplayRequest(mode=ReplayMode.WHAT_IF,
        process_model_revision=2 if algorithm.endswith('kf6') else None)
    result = Replay_Execute(plugin, opened.dataset, request)
    store = ReplayResultStore(); entry = store.Result_Add(result)
    document = _Document_Build(opened, tmp_path/'project.ssflp')
    document.replay_configurations[entry.result_id] = {
        'algorithm_id':result.algorithm_id,'algorithm_version':result.algorithm_version,
        'mode':entry.mode.value,'input_source':result.input_source,
        'actual_values':dict(result.parameters),
        'parameter_schema_identity':result.diagnostics['parameter_schema_identity'],
        'provenance':result.diagnostics['config_source']}
    if result.diagnostics.get('process_model_revision') is not None:
        document.replay_configurations[entry.result_id]['process_model_revision'] = result.diagnostics['process_model_revision']
    return opened, document, store


def test_save_cannot_rebind_old_computation_to_changed_log(tmp_path):
    opened, document, store = _SmallRun(tmp_path)
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    before = document.project_path.read_bytes()
    raw = opened.dataset.source_path.read_bytes()
    opened.dataset.source_path.write_bytes(raw[:-1] + bytes([raw[-1]^1]))
    with pytest.raises(ValueError, match='source_identity_invalid'):
        Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    assert document.project_path.read_bytes() == before


def test_file_replacement_before_replay_does_not_relabel_parsed_arrays(tmp_path):
    opened=NavigationPair_Open(tmp_path/'pair',flight_samples=21)
    parsed_identity=opened.dataset.metadata['parse_identity']
    replacement=NavigationPair_Open(tmp_path/'pair',flight_samples=81)
    assert replacement.dataset.metadata['parse_identity'] != parsed_identity
    result=Replay_Execute(builtin_registry().Algorithm_Get('silverstar.algorithm.pure_ins'),
        opened.dataset,ReplayRequest(mode=ReplayMode.WHAT_IF))
    assert result.diagnostics['input_identity'] == parsed_identity
    assert result.diagnostics['input_identity'] != replacement.dataset.metadata['parse_identity']
    store=ReplayResultStore();store.Result_Add(result)
    document=_Document_Build(opened,tmp_path/'replaced.ssflp')
    with pytest.raises(ValueError,match='source_.*mismatch|source_identity_invalid'):
        Project_Save(document,document.project_path,dataset=opened.dataset,replay_store=store)
    assert not document.project_path.exists()


@pytest.mark.parametrize('change',['append','cancel'])
def test_cache_hit_rechecks_source_and_cancellation_before_publication(tmp_path,monkeypatch,change):
    from silverstar_flp.core import parse_cache
    from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
    from silverstar_flp.log_open import LogOpenCoordinator,LogOpenRequest,LogOpenSourceMode
    opened,document,store=_SmallRun(tmp_path)
    Project_Save(document,document.project_path,dataset=opened.dataset,replay_store=store)
    read=parse_cache.DatasetCache_Read;context=TaskContext()
    def changed(*args,**kwargs):
        cached=read(*args,**kwargs)
        if change=='append':
            with opened.dataset.source_path.open('ab') as f:f.write(b'x')
        else:context.Cancel_Request()
        return cached
    monkeypatch.setattr(parse_cache,'DatasetCache_Read',changed)
    request=LogOpenRequest(opened.dataset.source_path,opened.source_package_path,
        source_mode=LogOpenSourceMode.PROJECT,project_path=document.project_path,
        dataset_cache_reference=document.parse_artifact)
    with pytest.raises(ValueError if change=='append' else TaskCancelledError,
                       match='log_source_changed|task_cancelled'):
        LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(tmp_path/'isolated-cache')).Open(request,context)


def test_legal_kf6_revision_two_cannot_restore_under_revision_one_config(tmp_path):
    opened, document, store = _SmallRun(tmp_path, 'silverstar.algorithm.kf6')
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    payload = json.loads(document.project_path.read_text())
    next(iter(payload['replay_configurations'].values()))['process_model_revision'] = 1
    document.project_path.write_text(json.dumps(payload))
    loaded = Project_Load(document.project_path)  # both 1 and 2 are legitimate schema values
    with pytest.raises(ValueError, match='configuration_mismatch'):
        ProjectResults_Load(loaded)


def test_save_data_toggle_retains_files_configurations_and_can_enable_again(tmp_path):
    opened, document, store = _SmallRun(tmp_path)
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    old_files = {p:p.read_bytes() for p in document.project_path.parent.glob('*.artifacts/**/*') if p.is_file()}
    document.save_data_and_results = False
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    loaded = Project_Load(document.project_path)
    assert not loaded.save_data_and_results
    assert loaded.result_artifact is None and loaded.parse_artifact is None
    assert loaded.replay_configurations == document.replay_configurations
    assert all(p.read_bytes() == value for p,value in old_files.items())
    assert not ProjectResults_Load(loaded).Entries_Get()
    loaded.save_data_and_results = True
    Project_Save(loaded, tmp_path/'save-as'/'again.ssflp', dataset=opened.dataset, replay_store=store)
    assert len(ProjectResults_Load(Project_Load(loaded.project_path)).Entries_Get()) == 1


def test_low_space_precheck_preserves_previous_document(tmp_path, monkeypatch):
    opened, document, store = _SmallRun(tmp_path)
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    before = document.project_path.read_bytes()
    monkeypatch.setattr(artifacts.shutil, 'disk_usage', lambda _:SimpleNamespace(free=0))
    with pytest.raises(ValueError, match='disk_space_insufficient'):
        Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    assert document.project_path.read_bytes() == before


def test_scalar_tag_cannot_allocate_or_expand_an_array(tmp_path):
    path = tmp_path/'project.ssflp'
    reference = artifacts.Artifact_Write(path, np.arange(3,dtype=np.float32), {})
    manifest = tmp_path/reference['path']
    payload = json.loads(gzip.decompress(manifest.read_bytes()))
    payload['payload'] = {'scalar':'<f8','value':payload['payload']}
    manifest.write_bytes(gzip.compress(json.dumps(payload).encode()))
    reference['sha256'] = artifacts.FileHash_Get(manifest)
    with pytest.raises(ValueError, match='scalar_invalid'):
        artifacts.Artifact_Read(path, reference, {})


def test_live_budget_counts_every_timeseries_copy_and_rejects_zero_row_width(tmp_path, monkeypatch):
    path = tmp_path/'project.ssflp'
    def series():
        return TimeSeries(np.arange(4,dtype=np.uint64), np.ones((4,3)), 'm','position',
                          'test',np.ones(4,dtype=bool),('E','N','U'))
    reference = artifacts.Artifact_Write(path, (series(),series()), {})
    monkeypatch.setattr(artifacts, 'MAX_LIVE_BYTES', 300)
    with pytest.raises(ValueError, match='live_memory_limit'):
        artifacts.Artifact_Read(path, reference, {})
    with pytest.raises(ValueError, match='array_invalid'):
        artifacts.Artifact_Write(path,np.empty((0,artifacts.MAX_COLUMNS+1)),{})


def test_precancel_does_not_stat_or_hash_any_file(tmp_path, monkeypatch):
    context=TaskContext(); context.Cancel_Request()
    monkeypatch.setattr(Path,'lstat',lambda *_:pytest.fail('No file inspection after pre-cancel'))
    with pytest.raises(TaskCancelledError):
        artifacts.Artifact_Read(tmp_path/'project.ssflp',{},context=context)


@pytest.mark.parametrize('kind',['fifo','reparse'])
def test_reader_rejects_nonregular_or_reparse_before_open(tmp_path, monkeypatch, kind):
    path=tmp_path/'manifest'; path.write_bytes(b'never read')
    info=SimpleNamespace(st_mode=stat.S_IFIFO if kind=='fifo' else stat.S_IFREG,
                         st_file_attributes=0x400 if kind=='reparse' else 0,st_size=10)
    monkeypatch.setattr(Path,'lstat',lambda *_:info)
    monkeypatch.setattr(Path,'open',lambda *_args,**_kwargs:pytest.fail('Must not open rejected node'))
    with pytest.raises(ValueError,match='file_not_regular'):
        artifacts.FileHash_Get(path)


def test_configuration_only_missing_primary_stays_unavailable(qtbot,tmp_path,monkeypatch):
    from silverstar_flp.ui.main_window import MainWindow
    opened,document,store=_SmallRun(tmp_path)
    entry=store.Entries_Get()[0]
    document.ui_state={'analysis_source':entry.source_id}
    document.save_data_and_results=False
    Project_Save(document,document.project_path,dataset=opened.dataset,replay_store=store)
    window=MainWindow(builtin_registry());qtbot.addWidget(window)
    errors=[];monkeypatch.setattr(window,'_Error_Show',errors.append)
    monkeypatch.setattr(window,'_ProjectChanges_Confirm',lambda:True)
    monkeypatch.setattr(window,'_Replay_Start',lambda *_:pytest.fail('No automatic replay'))
    window._LogOpenResult_Set(opened,Project_Load(document.project_path))
    assert window._replay_store.ActiveSource_Get().source_id==entry.source_id
    assert not window._channel_resolver.Source_Get().available
    assert not window.flight_page.position_plot.listDataItems()
    assert not window.flight_page.velocity_plot.listDataItems()
    assert errors and 'recompute_required' in errors[0]
    window._project_dirty=False;window.close()


@pytest.mark.parametrize('fault',['corrupt','parser_revision','changed_log'])
def test_parse_cache_faults_fall_back_only_to_strict_coordinator(tmp_path,monkeypatch,fault):
    from silverstar_flp.decoder_profiles.parser import DecoderProfileParserPlugin
    from silverstar_flp.core import parse_cache
    from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest, LogOpenSourceMode
    opened,document,store=_SmallRun(tmp_path)
    Project_Save(document,document.project_path,dataset=opened.dataset,replay_store=store)
    if fault=='corrupt':
        (document.project_path.parent/document.parse_artifact['path']).write_bytes(b'broken')
    elif fault=='parser_revision':
        monkeypatch.setattr(parse_cache,'ParserIdentity_Get',lambda:'a'*64)
    else:
        with opened.dataset.source_path.open('ab') as target:target.write(b'\x01')
    calls=[];original=DecoderProfileParserPlugin.parse
    def parse(self,*args,**kwargs):
        calls.append(1);return original(self,*args,**kwargs)
    monkeypatch.setattr(DecoderProfileParserPlugin,'parse',parse)
    result=LogOpenCoordinator(builtin_registry()).Open(LogOpenRequest(opened.dataset.source_path,
        opened.source_package_path,source_mode=LogOpenSourceMode.PROJECT,
        project_path=document.project_path,dataset_cache_reference=document.parse_artifact))
    assert calls==[1] and result.match_mode=='exact_generation_profile'


def test_manual_cache_cleanup_preserves_active_results_and_unknown_files(tmp_path):
    from silverstar_flp.core.project_cache import ProjectCache_Inspect, ProjectCache_ParseClear, ProjectCache_UnusedRemove
    opened,document,store=_SmallRun(tmp_path)
    Project_Save(document,document.project_path,dataset=opened.dataset,replay_store=store)
    inventory=ProjectCache_Inspect(document.project_path)
    assert inventory['physical_bytes']>0
    result=next(item for item in inventory['generations'] if item['role']=='saved_results')
    parse=next(item for item in inventory['generations'] if item['role']=='parsed_dataset')
    with pytest.raises(ValueError,match='protected'):
        ProjectCache_UnusedRemove(document.project_path,result['generation'])
    ProjectCache_ParseClear(document.project_path)
    unreferenced=Path(inventory['root'])/parse['generation']
    evidence=unreferenced/'formal-evidence.txt';evidence.write_text('preserve')
    with pytest.raises(ValueError,match='not_verified'):
        ProjectCache_UnusedRemove(document.project_path,parse['generation'])
    assert evidence.read_text()=='preserve' and len(ProjectResults_Load(Project_Load(document.project_path)).Entries_Get())==1


def test_background_save_captures_option_and_keeps_gui_responsive(qtbot,tmp_path,monkeypatch):
    from PySide6.QtCore import QTimer
    from silverstar_flp.core.project import ProjectDocument
    from silverstar_flp.ui.main_window import MainWindow
    opened,document,store=_SmallRun(tmp_path)
    window=MainWindow(builtin_registry());qtbot.addWidget(window)
    errors=[];monkeypatch.setattr(window,'_Error_Show',errors.append)
    monkeypatch.setattr(window,'_ProjectChanges_Confirm',lambda:True)
    window._LogOpenResult_Set(opened,ProjectDocument())
    entry=store.Entries_Get()[0]
    window._replay_store.Result_Add(entry.result)
    ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(25)
    window._Project_Write(document.project_path,background=True,save_data=True)
    qtbot.waitUntil(lambda:window._active_worker is None,timeout=15000)
    timer.stop()
    assert ticks and not errors and Project_Load(document.project_path).save_data_and_results
    window._Project_Write(document.project_path,background=True,save_data=False)
    qtbot.waitUntil(lambda:window._active_worker is None,timeout=15000)
    assert not errors and not Project_Load(document.project_path).save_data_and_results
    assert window._project.result_artifact is None
    window._project_dirty=False;window.close()


def test_unsaved_close_save_waits_for_background_transaction(qtbot,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from silverstar_flp.ui.main_window import MainWindow
    opened,document,_=_SmallRun(tmp_path)
    window=MainWindow(builtin_registry());qtbot.addWidget(window)
    window._LogOpenResult_Set(opened,document)
    window._Project_SetDirty(True)
    errors=[];monkeypatch.setattr(window,'_Error_Show',errors.append)
    monkeypatch.setattr(QMessageBox,'warning',lambda *_:QMessageBox.StandardButton.Save)
    monkeypatch.setattr(window,'_Project_Save',lambda:window._Project_Write(
        document.project_path,background=True,save_data=False))
    assert window._ProjectChanges_Confirm()
    assert not errors and window._active_worker is None
    assert document.project_path.is_file() and not window._project_dirty
    window.close()
