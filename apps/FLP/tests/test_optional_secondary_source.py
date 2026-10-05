"""Tiny published-channel fixtures; no numerical replay or hardware claims."""
from dataclasses import replace
from types import SimpleNamespace
import json
import hashlib

import numpy as np
import pytest
from PySide6.QtCore import Qt

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportLanguage, ExportOptions, ExportTheme, FlightExporter
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.charts import FlightPage
from silverstar_flp.ui.pages.replay import ReplayPage
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from silverstar_flp.ui.source_comparison import ComparisonSeries_Get
from tests.sslog_synthetic import AnalysisFlight_Build, START_TIMESTAMP_US


@pytest.fixture
def sample(tmp_path):
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path/'synthetic.BIN'))
    times = np.asarray([START_TIMESTAMP_US, START_TIMESTAMP_US+10000,
                        START_TIMESTAMP_US+20000], dtype=np.uint64)
    def series(values, unit, quantity, columns=()):
        return TimeSeries(times, np.tile(np.asarray(values,dtype=float),(3,1)), unit,
                          quantity, 'synthetic', np.ones(3,dtype=bool), columns,
                          {'frame':'ENU','origin_id':'task-origin','task_id':'synthetic'})
    channels = {
        'attitude.q_nb':series([1,0,0,0],'1','quaternion',('W','X','Y','Z')),
        'navigation.position_enu':series([0,1,2],'m','position',('E','N','U')),
        'navigation.velocity_enu':series([3,4,5],'m/s','velocity',('E','N','U')),
    }
    def result(algorithm='kf6', channels_override=None, parameters=None):
        return AlgorithmResult(algorithm if algorithm.startswith('silverstar.') else
                               'silverstar.algorithm.'+algorithm,
                               'synthetic','corrected_imu', parameters or {},
                               ReplayFidelity.APPROXIMATE,(),(),
                               channels_override or channels,{},'Offline')
    return dataset, channels, series, result


def test_secondary_default_none_and_full_run_identity(qtbot,sample):
    dataset, channels, _, result = sample
    store=ReplayResultStore()
    first=store.Result_Add(result('pure_ins'),algorithm_name='Pure INS')
    second=store.Result_Add(result('pure_ins'),algorithm_name='Pure INS')
    store.ActiveSource_Set(first.source_id)
    page=ReplayPage(Translator('en_US'),builtin_registry());qtbot.addWidget(page)
    page.Dataset_Set(dataset,store)
    assert page._secondary_source_id is None
    assert page.secondary_source_combo.currentData() is None
    assert first.source_id != second.source_id
    assert page.secondary_source_combo.findData(first.source_id) == -1
    assert page.secondary_source_combo.findData(second.source_id) >= 0
    before=page.Configuration_Get()
    requested=[];page.secondarySourceRequested.connect(requested.append)
    page.secondary_source_combo.setCurrentIndex(page.secondary_source_combo.findData(second.source_id))
    assert requested == [second.source_id]
    assert page.Configuration_Get() == before
    assert store.ActiveSource_Get().source_id == first.source_id
    page.analysis_source_combo.setCurrentIndex(page.analysis_source_combo.findData(second.source_id))
    assert page._secondary_source_id is None
    page.Dataset_Set(replace(dataset,source_path=dataset.source_path.with_name('next.BIN')),store)
    assert page._secondary_source_id is None


@pytest.mark.parametrize('change,reason',[
    ('missing','comparison.secondary_missing'),('primary_missing','comparison.primary_missing'),
    ('unit','comparison.incompatible'),('quantity','comparison.incompatible'),
    ('columns','comparison.incompatible'),('frame','comparison.incompatible'),
    ('origin_id','comparison.incompatible'),('task_id','comparison.incompatible'),
    ('no_overlap','comparison.no_overlap'),('invalid','comparison.no_overlap'),
    ('same','comparison.same_source'),('unknown','comparison.unavailable')])
def test_compatibility_never_fills_or_relabels_primary(sample,change,reason):
    dataset,channels,_,result=sample
    store=ReplayResultStore();a=store.Result_Add(result());b=store.Result_Add(result())
    store.ActiveSource_Set(a.source_id);resolver=ChannelResolver(dataset,store)
    primary=channels['navigation.position_enu'];secondary=primary;source_id=b.source_id
    if change=='missing':secondary=None
    elif change=='primary_missing':primary=None
    elif change=='unit':secondary=replace(secondary,unit='ft')
    elif change=='quantity':secondary=replace(secondary,quantity='innovation')
    elif change=='columns':secondary=replace(secondary,columns=('X','Y','Z'))
    elif change in ('frame','origin_id','task_id'):
        secondary=replace(secondary,metadata={**secondary.metadata,change:'different'})
    elif change=='no_overlap':secondary=replace(secondary,timestamp_us=secondary.timestamp_us+100000)
    elif change=='invalid':secondary=replace(secondary,valid=np.zeros(3,dtype=bool))
    elif change=='same':source_id=a.source_id
    elif change=='unknown':source_id='replay:gone'
    selected,note=ComparisonSeries_Get(primary,secondary,resolver,source_id)
    assert selected is None and note==reason


@pytest.mark.parametrize('invalid_kind', ['flag','nonfinite'])
def test_optional_flight_trace_uses_real_time_same_color_and_breaks(qtbot,sample,invalid_kind):
    dataset,channels,_,result=sample
    times=np.asarray([START_TIMESTAMP_US+5000,START_TIMESTAMP_US+10000,
                      START_TIMESTAMP_US+15000,START_TIMESTAMP_US+20000],dtype=np.uint64)
    secondary=replace(channels['navigation.position_enu'],timestamp_us=times,
        values=np.ones((4,3)),valid=np.asarray([True,False,True,True]),
        metadata={**channels['navigation.position_enu'].metadata,
                  'discontinuity_timestamps_us':(START_TIMESTAMP_US+20000,)})
    if invalid_kind=='nonfinite':
        values=secondary.values.copy();values[1]=np.nan
        secondary=replace(secondary,values=values,valid=np.ones(4,dtype=bool))
    store=ReplayResultStore();a=store.Result_Add(result());b=store.Result_Add(result(
        channels_override={**channels,'navigation.position_enu':secondary}))
    store.ActiveSource_Set(a.source_id);resolver=ChannelResolver(dataset,store)
    page=FlightPage(Translator('en_US'));qtbot.addWidget(page)
    page.Dataset_Set(dataset,resolver)
    assert len(page.position_plot.listDataItems())==3
    page.SecondarySource_Set(b.source_id);page.Dataset_Set(dataset,resolver)
    traces=page.position_plot.listDataItems();assert len(traces)==6
    for primary,other in zip(traces[:3],traces[3:]):
        assert primary.opts['pen'].style()==Qt.PenStyle.SolidLine
        assert other.opts['pen'].style()==Qt.PenStyle.DashLine
        assert primary.opts['pen'].color()==other.opts['pen'].color()
        assert 'Primary' in primary.name() and '#1' in primary.name()
        assert 'Secondary' in other.name() and '#2' in other.name()
        assert other.xData[0]==pytest.approx(.005)
        assert not np.any(other.opts['connect'])
    assert page._reference_position is None
    for language in ('zh_CN','en_US'):
        page.Language_Apply(Translator(language))
        for theme in ('dark','light'):
            page.Theme_Apply(theme);page.TimeRange_Set(START_TIMESTAMP_US+10000,START_TIMESTAMP_US+20000)
            page.reset_charts_button.click()
            assert len(page.position_plot.listDataItems())==6
    page.SecondarySource_Set(None);page.Dataset_Set(dataset,resolver)
    assert len(page.position_plot.listDataItems())==3


def test_state_groups_map_own_covariance_indices_and_primary_thresholds(qtbot,sample):
    dataset,channels,s,result=sample
    registry=builtin_registry()
    kf=registry.Algorithm_Get('silverstar.algorithm.kf6').metadata.estimator_visualization
    eskf_id='silverstar.algorithm.estimator.eskf15'
    eskf=registry.Algorithm_Get(eskf_id).metadata.estimator_visualization
    kg=kf.measurement_groups[0];eg=eskf.measurement_groups[0]
    primary={**channels,'kf6.covariance.diagonal':s([1,4,9,16,25,36],'mixed','covariance'),
             kg.innovation_channel:s([1,2],'m','innovation',('E','N')),
             kg.nis_channel:s([2],'1','nis')}
    other={**channels,'eskf15.covariance.diagonal':s([4,9,16,25,36,49]+[100]*9,'mixed','covariance'),
           eg.innovation_channel:s([3,4],'m','innovation',('E','N')),
           eg.nis_channel:s([9],'1','nis')}
    parameters={threshold.parameter_id:5+index for index,threshold in enumerate(kg.NisThresholds_Get())}
    store=ReplayResultStore();a=store.Result_Add(result(channels_override=primary,parameters=parameters))
    b=store.Result_Add(result(eskf_id,other,{key:999 for key in parameters}))
    store.ActiveSource_Set(a.source_id);resolver=ChannelResolver(dataset,store)
    page=StateEstimationPage(Translator('en_US'),registry);qtbot.addWidget(page)
    page.SecondarySource_Set(b.source_id);page.Dataset_Set(dataset,resolver)
    traces=page.covariance_plot.listDataItems();assert len(traces)==6
    assert np.allclose([t.yData[0] for t in traces[:3]],[2,3,4])
    assert np.allclose([t.yData[0] for t in traces[3:]],[1,2,3])
    for secondary,primary in zip(traces[:3],traces[3:]):
        assert secondary.opts['pen'].color()==primary.opts['pen'].color()
    assert len(page.innovation_plot.listDataItems())==4
    assert len(page.nis_plot.listDataItems())==2+len(parameters)
    assert not any(np.any(t.yData==999) for t in page.nis_plot.listDataItems())
    assert page._source_parameters==parameters
    store.ActiveSource_Set(b.source_id);page.SecondarySource_Set(a.source_id)
    page.Dataset_Set(dataset,resolver)
    position_note = page.comparison_note.text()
    page.state_group_combo.setCurrentIndex(page.state_group_combo.findData('attitude_error'))
    assert len(page.covariance_plot.listDataItems())==3
    assert all('Primary' in t.name() for t in page.covariance_plot.listDataItems())
    assert page.comparison_note.text() != position_note
    page.state_group_combo.setCurrentIndex(page.state_group_combo.findData('position'))
    assert len(page.covariance_plot.listDataItems())==6
    assert page.comparison_note.text() == position_note
    ins=store.Result_Add(result('pure_ins'));store.ActiveSource_Set(ins.source_id)
    page.Dataset_Set(dataset,resolver)
    assert all(not plot.listDataItems() for plot in page._Plots_Get())


def test_recorded_kf6_legacy_covariance_metadata_is_not_missing(qtbot,sample):
    # Metadata/shape reported by the exact decoder for real log 000027.
    # Values are synthetic; this regression does not claim real-log execution.
    dataset,channels,_,result=sample
    count=703
    legacy=TimeSeries(
        START_TIMESTAMP_US + np.arange(count,dtype=np.uint64)*10000,
        np.tile([1.,4.,9.,16.,25.,36.],(count,1)),
        '1','dimensionless','ESTIMATOR',np.ones(count,dtype=bool),
        ('PxE','PxN','PxU','PvE','PvN','PvU'))
    dataset=replace(dataset,series={**dataset.series,
        'kf6.recorded.covariance.diagonal':legacy})
    store=ReplayResultStore();store.ActiveSource_Set('recorded:kf6')
    page=StateEstimationPage(Translator('en_US'),builtin_registry());qtbot.addWidget(page)
    resolver=ChannelResolver(dataset,store)
    page.Dataset_Set(dataset,resolver)
    assert len(page.covariance_plot.listDataItems())==3
    assert np.allclose([trace.yData[0] for trace in page.covariance_plot.listDataItems()],[1,2,3])
    page.state_group_combo.setCurrentIndex(page.state_group_combo.findData('velocity'))
    assert np.allclose([trace.yData[0] for trace in page.covariance_plot.listDataItems()],[4,5,6])
    # Legacy scalar metadata is accepted only for the recorded KF6 contract.
    entry=store.Result_Add(result(channels_override={**channels,'kf6.covariance.diagonal':legacy}))
    store.ActiveSource_Set(entry.source_id);page.Dataset_Set(dataset,resolver)
    assert not page.covariance_plot.listDataItems()
    store.ActiveSource_Set('recorded:kf6');page.SecondarySource_Set(entry.source_id)
    page.Dataset_Set(dataset,resolver)
    assert len(page.covariance_plot.listDataItems())==3
    assert all('Primary' in trace.name() for trace in page.covariance_plot.listDataItems())


@pytest.mark.parametrize('change',['width','unit','quantity'])
def test_recorded_legacy_covariance_requires_exact_storage_contract(qtbot,sample,change):
    dataset,_,s,_=sample
    legacy=s([1,4,9,16,25,36],'1','dimensionless')
    if change=='width':legacy=replace(legacy,values=legacy.values[:,:3],columns=legacy.columns[:3])
    elif change=='unit':legacy=replace(legacy,unit='ft')
    else:legacy=replace(legacy,quantity='innovation')
    dataset=replace(dataset,series={**dataset.series,'kf6.recorded.covariance.diagonal':legacy})
    store=ReplayResultStore();store.ActiveSource_Set('recorded:kf6')
    page=StateEstimationPage(Translator('en_US'),builtin_registry());qtbot.addWidget(page)
    page.Dataset_Set(dataset,ChannelResolver(dataset,store))
    assert not page.covariance_plot.listDataItems()


def test_export_click_freezes_only_primary_even_if_follow_ui_has_stale_id(monkeypatch,sample,tmp_path):
    dataset,channels,_,result=sample
    store=ReplayResultStore();a=store.Result_Add(result());b=store.Result_Add(result())
    store.ActiveSource_Set(a.source_id);resolver=ChannelResolver(dataset,store)
    captured=[];errors=[]
    owner=SimpleNamespace(_dataset=dataset,_replay_store=store,_channel_resolver=resolver,
        _secondary_source_id=b.source_id,_theme='dark',_registry=builtin_registry(),
        explorer_page=SimpleNamespace(ExportChannels_Get=lambda:()),
        time_range=SimpleNamespace(controller=SimpleNamespace(model=SimpleNamespace(start=0,end=.02))),
        export_dialog=SimpleNamespace(Result_Error=errors.append),_Export_ResultSet=lambda _:None,
        _Task_Start=lambda worker,*_:captured.append(worker))
    calls=[]
    monkeypatch.setattr(FlightExporter,'export',lambda self,dataset,output,**kwargs:calls.append(kwargs))
    MainWindow._Export_Start(owner,tmp_path/'export',ExportOptions(source_mode='follow_ui',source_id=b.source_id))
    assert not errors and len(captured)==1
    store.ActiveSource_Set(b.source_id);owner._secondary_source_id=None
    captured[0]._function(captured[0].context)
    frozen=calls[0]['replay_store']
    assert calls[0]['options'].source_id==a.source_id
    assert tuple(entry.source_id for entry in frozen.Entries_Get())==(a.source_id,)
    assert frozen.ActiveSource_Get().source_id==a.source_id


@pytest.mark.parametrize('language,theme', [('en_US','light'),('en_US','dark'),
                                           ('zh_CN','light'),('zh_CN','dark')])
def test_secondary_toggle_preserves_actual_primary_csv_png_gif(sample,tmp_path,language,theme):
    dataset,channels,_,result=sample
    store=ReplayResultStore();primary=store.Result_Add(result('pure_ins'))
    secondary=store.Result_Add(result('pure_ins', {**channels,
        'navigation.position_enu':replace(channels['navigation.position_enu'],values=np.full((3,3),999.))}))
    store.ActiveSource_Set(primary.source_id);resolver=ChannelResolver(dataset,store)
    workers=[];errors=[]
    owner=SimpleNamespace(_dataset=dataset,_replay_store=store,_channel_resolver=resolver,
        _secondary_source_id=None,_theme=theme,_registry=builtin_registry(),
        explorer_page=SimpleNamespace(ExportChannels_Get=lambda:()),
        time_range=SimpleNamespace(controller=SimpleNamespace(model=SimpleNamespace(start=0,end=.02))),
        export_dialog=SimpleNamespace(Result_Error=errors.append),_Export_ResultSet=lambda _:None,
        _Task_Start=lambda worker,*_:workers.append(worker))
    options=ExportOptions(source_mode='follow_ui',language=ExportLanguage.FOLLOW_UI,
        ui_language=language,theme=ExportTheme.FOLLOW_UI,include_overview=False,
        include_events=False,include_diagnostics=False,include_full_covariance_keyframes=False,
        include_trajectory_3d=False,include_attitude_gif=True,include_csv=True,include_plots=True,
        page_mode='Full',gif_range_mode='Full')
    hashes=[]
    for selected,name in ((None,'off'),(secondary.source_id,'on')):
        owner._secondary_source_id=selected
        output=tmp_path/name
        MainWindow._Export_Start(owner,output,options)
        assert not errors
        manifest=workers[-1]._function(workers[-1].context)
        assert not manifest.failures
        payload=json.loads(next(output.glob('Export_Manifest*.json')).read_text(encoding='utf-8'))
        assert payload['active_analysis_source']==primary.source_id
        assert secondary.source_id not in json.dumps(payload)
        hashes.append({str(path.relative_to(output)):hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in output.rglob('*') if path.suffix in ('.png','.csv','.gif')})
    assert hashes[0]==hashes[1]
    assert all(any(name.endswith(suffix) for name in hashes[0]) for suffix in ('.png','.csv','.gif'))
