"""Small published-role comparison regressions; no long numerical replay."""
from dataclasses import replace
import numpy as np
import pytest
from PySide6.QtCore import Qt
import pyqtgraph as pg
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.charts import FlightPage, _Series_Plot, TraceColorAllocator
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from silverstar_flp.ui.source_comparison import NavigationComparisonSeries_Get
from tests.test_optional_secondary_source import sample
from tests.sslog_synthetic import START_TIMESTAMP_US

ALGORITHMS=('pure_ins','sf6','kf6','silverstar.algorithm.estimator.eskf15')

@pytest.mark.parametrize('first,second',[(a,b) for a in ALGORITHMS for b in ALGORITHMS if a!=b]+[('pure_ins','pure_ins')])
def test_every_builtin_direction_has_position_velocity_attitude_height(qtbot,sample,first,second):
    dataset,channels,_,result=sample
    store=ReplayResultStore();a=store.Result_Add(result(first));b=store.Result_Add(result(second))
    store.ActiveSource_Set(a.source_id)
    page=FlightPage(Translator('en_US'));qtbot.addWidget(page)
    page.SecondarySource_Set(b.source_id);page.Dataset_Set(dataset,ChannelResolver(dataset,store))
    for plot,width in ((page.position_plot,3),(page.velocity_plot,3),(page.quaternion_plot,4),(page.euler_plot,3)):
        traces=plot.listDataItems();assert len(traces)==width*2
        assert sum(t.opts['pen'].style()==Qt.PenStyle.DashLine for t in traces)==width
        assert any('Primary' in t.name() for t in traces) and any('Secondary' in t.name() for t in traces)
    assert np.array_equal(page.position_plot.listDataItems()[-1].yData,channels['navigation.position_enu'].values[:,2])
    # Shared device IMU has no independent algorithm result to borrow.
    assert not any('Secondary' in t.name() for t in page.acceleration_plot.listDataItems())

@pytest.mark.parametrize('recorded_primary',[False,True])
def test_known_recorded_roles_and_own_legacy_covariance_compare(qtbot,sample,recorded_primary):
    dataset,channels,s,result=sample
    legacy=replace(s([1,4,9,16,25,36],'1','dimensionless'),columns=('PxE','PxN','PxU','PvE','PvN','PvU'))
    dataset=replace(dataset,series={**dataset.series,
        'kf6.recorded.navigation.position_enu':replace(channels['navigation.position_enu'],quantity='length'),
        'kf6.recorded.navigation.velocity_enu':channels['navigation.velocity_enu'],
        'kf6.recorded.attitude.q_nb':replace(channels['attitude.q_nb'],quantity='dimensionless'),
        'kf6.recorded.covariance.diagonal':legacy})
    store=ReplayResultStore();entry=store.Result_Add(result(channels_override={**channels,
        'kf6.covariance.diagonal':s([4,9,16,25,36,49],'mixed','covariance')}))
    store.ActiveSource_Set('recorded:kf6' if recorded_primary else entry.source_id)
    secondary=entry.source_id if recorded_primary else 'recorded:kf6';resolver=ChannelResolver(dataset,store)
    page=FlightPage(Translator('en_US'));qtbot.addWidget(page);page.SecondarySource_Set(secondary);page.Dataset_Set(dataset,resolver)
    assert [len(p.listDataItems()) for p in (page.position_plot,page.velocity_plot,page.quaternion_plot,page.euler_plot)]==[6,6,8,6]
    state=StateEstimationPage(Translator('en_US'),builtin_registry());qtbot.addWidget(state)
    state.SecondarySource_Set(secondary);state.Dataset_Set(dataset,resolver)
    for group in ('position','velocity'):
        state.state_group_combo.setCurrentIndex(state.state_group_combo.findData(group))
        assert len(state.covariance_plot.listDataItems())==6
    assert legacy.quantity=='dimensionless' and legacy.unit=='1'
    foreign=replace(channels['navigation.position_enu'],quantity='length',metadata={'origin_id':'other'})
    assert NavigationComparisonSeries_Get('navigation.position_enu',channels['navigation.position_enu'],foreign,resolver,secondary)[0] is None

@pytest.mark.parametrize('reverse',[False,True])
def test_baro_role_mapping_covers_innovation_nis_sigma_and_lag(qtbot,sample,reverse):
    dataset,channels,s,result=sample;registry=builtin_registry()
    ids=('silverstar.algorithm.kf6','silverstar.algorithm.estimator.eskf15')
    specs=[registry.Algorithm_Get(a).metadata.estimator_visualization for a in ids]
    groups=[next(g for g in spec.measurement_groups if g.measurement_group_id=='barometric_altitude') for spec in specs]
    runs=[]
    for index,(algo,g) in enumerate(zip(ids,groups)):
        own={**channels,g.innovation_channel:s([1],'m','innovation',g.component_names),
             g.nis_channel:s([2],'1','nis'),g.measurement_age_channel:s([3],'ms','receive_age'),
             g.fixed_lag_latency_channel:s([4],'ms','fixed_lag_latency' if index==0 else 'latency'),
             g.measurement_uncertainty_channel:s([9],'m^2' if index==0 else 'mixed','variance' if index==0 else 'input_variance'),
             g.effective_r_channel:s([16],'m^2' if index==0 else 'mixed','variance' if index==0 else 'effective_variance')}
        runs.append(result(algo,own))
    if reverse:runs.reverse()
    store=ReplayResultStore();a=store.Result_Add(runs[0]);b=store.Result_Add(runs[1]);store.ActiveSource_Set(a.source_id)
    page=StateEstimationPage(Translator('en_US'),registry);qtbot.addWidget(page)
    page.SecondarySource_Set(b.source_id);page.Dataset_Set(dataset,ChannelResolver(dataset,store))
    for combo in (page.innovation_measurement_combo,page.nis_measurement_combo,page.measurement_group_combo):
        combo.setCurrentIndex(combo.findData('barometric_altitude'))
    for plot,count in ((page.innovation_plot,1),(page.nis_plot,1),(page.measurement_uncertainty_plot,2),(page.measurement_age_plot,2)):
        assert sum('Secondary' in (t.name() or '') for t in plot.listDataItems())==count
    group=page._MeasurementGroup_Get(page.measurement_group_combo)
    bad=replace(s([9],'ft^2','variance'),metadata={})
    assert page._MeasurementRole_Normalize(bad,group,'measurement_uncertainty_channel') is None
    assert page._MeasurementRole_Normalize(s([9],'1','dimensionless'),group,'measurement_uncertainty_channel') is None

def test_reset_rejected_and_duplicate_timestamps_do_not_connect_epochs(qtbot):
    reset=START_TIMESTAMP_US+np.asarray([0,10000,5000],dtype=np.uint64)
    with pytest.raises(ValueError,match='monotonic'):
        TimeSeries(reset,np.arange(3),'m','position','tiny',np.ones(3,dtype=bool))
    t=START_TIMESTAMP_US+np.asarray([0,10000,10000,15000,15000,25000],dtype=np.uint64)
    series=TimeSeries(t,np.arange(6,dtype=float),'m','position','tiny',np.ones(6,dtype=bool))
    plot=pg.PlotWidget();qtbot.addWidget(plot)
    _Series_Plot(plot,series,START_TIMESTAMP_US,colors=TraceColorAllocator(),reference=True)
    trace=plot.listDataItems()[0]
    assert not trace.opts['connect'][1] and not trace.opts['connect'][3]
    np.testing.assert_allclose(trace.xData,np.asarray([0,.01,.01,.015,.015,.025]),rtol=0,atol=1e-16)
