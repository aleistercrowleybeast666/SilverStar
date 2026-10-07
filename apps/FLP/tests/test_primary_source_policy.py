"""Small synthetic red regressions for the requested source policy. No replay math."""
import os, sys
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO)]
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from silverstar_flp.ui.navigation_diagnostics import NavigationDiagnostics
from silverstar_flp.export.service import FlightExporter
from tests.sslog_synthetic import AnalysisFlight_Build, START_TIMESTAMP_US
from tests.test_navigation_diagnostics import _Dataset_Build, _Resolver_Build

@pytest.fixture(scope='module')
def app():
    application=QApplication.instance() or QApplication([])
    application._policy_widgets=[]
    return application

@pytest.fixture
def setup(tmp_path,app):
    dataset=Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path/'SYNTHETIC.BIN'))
    timestamps=np.array([START_TIMESTAMP_US,START_TIMESTAMP_US+10000],dtype=np.uint64)
    def s(v,unit,quantity,columns):
        return TimeSeries(timestamps,np.array([v,v],dtype=float),unit,quantity,'fake',np.ones(2,dtype=bool),columns)
    channels={'attitude.q_nb':s([1,0,0,0],'1','quaternion',('W','X','Y','Z')),
              'navigation.position_enu':s([0,0,0],'m','position',('E','N','U')),
              'navigation.velocity_enu':s([0,0,0],'m/s','velocity',('E','N','U'))}
    def fake(algorithm):
        return AlgorithmResult('silverstar.algorithm.'+algorithm,'fake','corrected_imu',{},ReplayFidelity.APPROXIMATE,(),(),channels,{},'Offline')
    return dataset,channels,fake

@pytest.mark.parametrize('algorithm',['pure_ins','sf6'])
def test_main_without_filter_metadata_must_not_show_recorded_kf6(setup,algorithm):
    dataset,channels,fake=setup
    store=ReplayResultStore();entry=store.Result_Add(fake(algorithm),algorithm_name=algorithm)
    store.ActiveSource_Set(entry.source_id)
    page=StateEstimationPage(Translator('en_US'),builtin_registry())
    QApplication.instance()._policy_widgets.append(page)
    page.show()
    QApplication.processEvents()
    try:
        page.Dataset_Set(dataset,ChannelResolver(dataset,store))
        # Main source has no covariance. No replacement filter's curve is permitted.
        assert len(page.covariance_plot.listDataItems()) == 0
        assert len(page.nis_plot.listDataItems()) == 0
        assert page._estimator_source is None or page._estimator_source.source_id == entry.source_id
    finally:
        page.close()

def test_unknown_explicit_source_must_return_no_series(setup):
    dataset,_,_=setup
    resolver=ChannelResolver(dataset,ReplayResultStore())
    # UI/export must handle unavailability; no silent recorded substitution.
    assert resolver.Series_Get('kf6.covariance.diagonal','replay:deleted') is None

def test_recorded_final_solution_must_not_borrow_another_estimator(setup):
    dataset,channels,_=setup
    mixed=replace(dataset,series={**dataset.series,
        'sf6.recorded.navigation.position_enu':channels['navigation.position_enu'],
        'sf6.recorded.navigation.velocity_enu':channels['navigation.velocity_enu'],
        'sf6.recorded.attitude.q_nb':channels['attitude.q_nb']})
    page=StateEstimationPage(Translator('en_US'),builtin_registry())
    QApplication.instance()._policy_widgets.append(page)
    page.show()
    QApplication.processEvents()
    try:
        page.Dataset_Set(mixed,ChannelResolver(mixed,ReplayResultStore()))
        assert len(page.covariance_plot.listDataItems()) == 0
        assert page._estimator_source is None or page._estimator_source.algorithm_id.endswith('.sf6')
        assert 'SF6' in page.source_value_label.text()
    finally:
        page.close()

def test_export_snapshot_has_only_primary_run_and_no_filter_fallback(setup):
    dataset,_,fake=setup
    store=ReplayResultStore()
    primary=store.Result_Add(fake('pure_ins'),algorithm_name='Pure INS')
    secondary=store.Result_Add(fake('pure_ins'),algorithm_name='Pure INS')
    assert primary.source_id != secondary.source_id
    assert (primary.run_index,secondary.run_index)==(1,2)
    store.ActiveSource_Set(primary.source_id)
    snapshot=store.Snapshot_Create(primary.source_id)
    assert tuple(e.source_id for e in snapshot.Entries_Get())==(primary.source_id,)
    assert FlightExporter()._EstimatorSelection_Get(ChannelResolver(dataset,snapshot)) is None

def test_valid_replay_missing_channel_is_already_strict(setup):
    dataset,_,fake=setup
    store=ReplayResultStore();entry=store.Result_Add(fake('sf6'),algorithm_name='SF6')
    store.ActiveSource_Set(entry.source_id)
    assert ChannelResolver(dataset,store).Series_Get('kf6.covariance.diagonal',entry.source_id) is None

@pytest.mark.parametrize('algorithm',['pure_ins','sf6'])
def test_dormant_gnss_component_must_not_substitute_board_filter(app,algorithm):
# This widget is currently not mounted in ed9fe9b StateEstimationPage.
    page=NavigationDiagnostics('gnss',Translator('en_US'))
    QApplication.instance()._policy_widgets.append(page)
    try:
        entry=SimpleNamespace(algorithm_id='silverstar.algorithm.'+algorithm,run_index=1,diagnostics={})
        page.Dataset_Set(_Dataset_Build(),_Resolver_Build(entry))
        assert page.model.rowCount()==0
    finally:
        page.close()

def test_switch_clears_every_primary_diagnostic_and_unknown_selection(setup):
    dataset, channels, fake = setup
    store = ReplayResultStore()
    primary_channels = {**channels, **{
        name.replace('.recorded.', '.'): series
        for name, series in dataset.series.items() if name.startswith('kf6.recorded.')
    }}
    kf = store.Result_Add(replace(fake('kf6'), channels=primary_channels))
    ins = store.Result_Add(fake('pure_ins'))
    sf = store.Result_Add(fake('sf6'))
    page = StateEstimationPage(Translator('en_US'), builtin_registry())
    QApplication.instance()._policy_widgets.append(page)
    resolver = ChannelResolver(dataset, store)
    try:
        for source_id in (kf.source_id, ins.source_id, sf.source_id, kf.source_id):
            assert store.ActiveSource_Set(source_id)
            page.Dataset_Set(dataset, resolver)
            if source_id == kf.source_id:
                assert page.covariance_plot.listDataItems()
                page.navigation_health_label.setText('old health')
                page.measurement_unavailable_label.setText('old measurement')
                page.gnss_integrity._window_evidence = [{'valid': False}]
            else:
                assert all(not plot.listDataItems() for plot in page._Plots_Get())
                assert not page.navigation_health_label.text()
                assert not page.measurement_unavailable_label.text()
                assert page.gnss_integrity._parameters == {}
                assert page.gnss_integrity._window_evidence is None
                assert page.gnss_integrity._result is None
                assert all(page.nis_summary.item(r,c) is None
                           for r in range(page.nis_summary.rowCount())
                           for c in range(page.nis_summary.columnCount()))
                page.Language_Apply(Translator('zh_CN'))
                page.Theme_Apply('dark')
                page.TimeRange_Set(0, .01)
                page._ChartViews_Reset()
                assert not page.covariance_plot.listDataItems()
        store._active_source_id = 'replay:deleted'
        page.Dataset_Set(dataset, resolver)
        assert 'replay:deleted' in page.source_value_label.text()
        assert not page.covariance_plot.listDataItems()
        assert resolver.Series_Get('navigation.position_enu') is None
    finally:
        page.close()

def test_mixed_recorded_snapshot_is_solution_exclusive(setup):
    dataset, channels, _ = setup
    mixed = replace(dataset, series={**dataset.series, **{
        'sf6.recorded.' + name: series for name, series in channels.items()
    }})
    resolver = ChannelResolver(mixed, ReplayResultStore())
    source = resolver.Source_Get()
    assert source.source_id == 'recorded:sf6'
    assert source.recorded_solution_id == 'sf6'
    snapshot = resolver.store.Snapshot_Create(source.source_id)
    frozen = ChannelResolver(mixed, snapshot)
    assert frozen.Source_Get().source_id == 'recorded:sf6'
    assert FlightExporter()._EstimatorSelection_Get(frozen) is None
    exported = FlightExporter()._SourceChannels_Get(frozen)
    assert not any(name.startswith('kf6.') for name in exported)
    assert frozen.Series_Get('kf6.covariance.diagonal') is None
    assert frozen.Series_Get('navigation.position_enu') is channels['navigation.position_enu']


