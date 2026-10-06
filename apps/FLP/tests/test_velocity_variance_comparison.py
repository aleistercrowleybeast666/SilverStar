"""Exercise the actual KF6 channel producer without numerical replay."""
from dataclasses import replace
import numpy as np
import pytest
from silverstar_flp.analysis.measurement_diagnostics import RecomputedMeasurementChannels_Build
from silverstar_flp.core.analysis_source import ChannelResolver,ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.sslog_synthetic import START_TIMESTAMP_US
from tests.test_optional_secondary_source import sample

KF6='silverstar.algorithm.kf6'
ESKF='silverstar.algorithm.estimator.eskf15'
ROLES=('measurement_uncertainty_channel','effective_r_channel')

def _PublishedChannels_Build(group_name):
    width=2 if group_name.endswith('_en') else 1
    rows=[{'group':group_name,'timestamp_us':START_TIMESTAMP_US+i*10000,'valid':True,
           'input_variance':tuple([9.]*width),'effective_variance':tuple([16.]*width),
           'receive_age':2.,'fixed_lag_latency':3.,'r_scale':16./9.} for i in range(3)]
    return RecomputedMeasurementChannels_Build(rows)

@pytest.mark.parametrize('group_id',['gnss_velocity_en','gnss_velocity_u'])
@pytest.mark.parametrize('pair',[(KF6,ESKF),(ESKF,KF6),(KF6,KF6)])
def test_published_velocity_variance_has_both_sigma_sources(qtbot,sample,group_id,pair):
    dataset,channels,_,result=sample;registry=builtin_registry()
    kg=next(g for g in registry.Algorithm_Get(KF6).metadata.estimator_visualization.measurement_groups
            if g.measurement_group_id==group_id)
    published=_PublishedChannels_Build(group_id.removeprefix('gnss_'))
    for role in ROLES:
        series=published[getattr(kg,role)]
        assert series.unit=='m^2/s^2' and series.quantity=='variance'
        assert series.metadata['group_specific'] and series.source=='measurement_operation'
    store=ReplayResultStore();entries=[]
    for algo in pair:
        group=next(g for g in registry.Algorithm_Get(algo).metadata.estimator_visualization.measurement_groups
                   if g.measurement_group_id==group_id)
        own={**channels}
        for role,quantity in zip(ROLES,('input_variance','effective_variance')):
            series=published[getattr(kg,role)]
            own[getattr(group,role)]=(series if algo==KF6 else
                replace(series,unit='mixed',quantity=quantity,columns=tuple(f'[{i}]' for i in range(group.dimension))))
        entries.append(store.Result_Add(result(algo,own)))
    store.ActiveSource_Set(entries[0].source_id)
    page=StateEstimationPage(Translator('en_US'),registry);qtbot.addWidget(page)
    page.SecondarySource_Set(entries[1].source_id);page.Dataset_Set(dataset,ChannelResolver(dataset,store))
    page.measurement_group_combo.setCurrentIndex(page.measurement_group_combo.findData(group_id))
    secondary=[t for t in page.measurement_uncertainty_plot.listDataItems() if 'Secondary' in (t.name() or '')]
    primary=[t for t in page.measurement_uncertainty_plot.listDataItems() if 'Primary' in (t.name() or '')]
    assert len(secondary)==2*kg.dimension and len(primary)==2*kg.dimension
    for traces in (secondary,primary):
        assert sorted(float(t.yData[0]) for t in traces)==[3.]*kg.dimension+[4.]*kg.dimension

@pytest.mark.parametrize('group_id',['gnss_velocity_en','gnss_velocity_u'])
@pytest.mark.parametrize('role',ROLES)
@pytest.mark.parametrize('unit',['m/s^2','m/s2','m^2','ft^2/s^2','mixed'])
def test_velocity_variance_rejects_acceleration_and_foreign_units(group_id,role,unit):
    group=next(g for g in builtin_registry().Algorithm_Get(KF6).metadata.estimator_visualization.measurement_groups
               if g.measurement_group_id==group_id)
    original=_PublishedChannels_Build(group_id.removeprefix('gnss_'))[getattr(group,role)]
    assert StateEstimationPage._MeasurementRole_Normalize(replace(original,unit=unit),group,role) is None

def test_velocity_variance_unit_cannot_relabel_position_group():
    group=next(g for g in builtin_registry().Algorithm_Get(KF6).metadata.estimator_visualization.measurement_groups
               if g.measurement_group_id=='gnss_position_en')
    series=_PublishedChannels_Build('velocity_en')['kf6.measurement_input_variance.velocity_en']
    assert StateEstimationPage._MeasurementRole_Normalize(series,group,ROLES[0]) is None
