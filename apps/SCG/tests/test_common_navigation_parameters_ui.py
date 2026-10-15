"""Visibility changes must not change declarative values or introduce features."""
import pytest
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage
from silverstar_fccg.ui.widgets import CollapsibleSection


@pytest.mark.parametrize('kind',['kf6','eskf15','sf6'])
@pytest.mark.parametrize('language',['zh_CN','en_US'])
def test_common_parameters_visible_advanced_collapsed(builtin_catalog,qapp,kind,language):
    owner=builtin_catalog.Component_Get('silverstar.algorithm.estimator.'+kind)
    values={owner.component_id:{p.parameter_id:p.default for p in owner.algorithm_parameters}}
    before={key:dict(value) for key,value in values.items()}
    page=NavigationConfigurationPage(Translator(language))
    page.Configuration_Set((owner,),values)
    page.show();qapp.processEvents()
    common=(('gain_ve','gain_pu') if kind=='sf6' else
            ('gnss_position_std_horizontal','baro_std_m','gnss_velocity_measurement_delay_ms',
             'nis_soft_enabled','nis_hard_enabled'))
    for name in common:
        editor=page.editors[(owner.component_id,name)]
        assert editor.isVisible()
        parent=editor.parentWidget()
        while parent is not page:
            assert not isinstance(parent,CollapsibleSection)
            parent=parent.parentWidget()
    if kind!='sf6':
        assert not page.editors[(owner.component_id,'p0_position_e')].isVisible()
        assert all(not section.Expanded_Is() for section in page._content.findChildren(CollapsibleSection))
    else:
        assert not any('delay' in name or 'nis_' in name for _,name in page.editors)
    assert values==before
    page.close()
