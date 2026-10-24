from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile, StrategyAvailabilities_Get
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _LogMetadataDeclarations_Get
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.ui.main_window import MainWindow

APP = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('algorithm', ['eskf20','inekf15','inekf20'])
def test_experimental_selection_dependency_closure_generation_and_identity(tmp_path,qapp,algorithm):
    service=FccgService(APP);service.policy=WorkspacePolicy(APP.parents[1])
    window=MainWindow(SettingsStore(tmp_path/'settings.ini'),service=service)
    window._model=service.ReferenceProject_Create('Experimental_'+algorithm)
    window._Project_Refresh()
    errors=[];window._Error_Show=errors.append
    identity='silverstar.algorithm.estimator.'+algorithm
    try:
        combo=window.flight_configuration_page.strategy_combos['estimator']
        index=combo.findData(identity)
        assert index>=0 and combo.model().item(index).isEnabled()
        assert '实验' in combo.itemText(index) or 'experimental' in combo.itemText(index)
        combo.setCurrentIndex(index);qapp.processEvents()
        model=window._model
        assert model.strategies['estimator']==identity and not errors
        assert 'silverstar.algorithm.augmented.common' in model.base_components
        assert model.algorithm_parameters[identity]['software_validation_build']==1
        assert model.algorithm_parameters[identity]['initialization_confirmed']==0
        result=Project_Validate(model,service.catalog)
        assert result.valid,[row for row in result.issues if row.level=='error']
        assert any(row.code=='TIMING_PROFILE_UNQUALIFIED' and row.level=='warning' for row in result.issues)
        assert any(row.code=='EXPERIMENTAL_ESTIMATOR_UNVERIFIED' for row in result.issues)
        header=_FlightConfigHeader_Render(model,service.catalog)
        assert '#define' in header
        graph=SourceGraph_Resolve(model,service.catalog)
        assert 'Algorithm/Estimator/Augmented/Src/navigation_augmented_backend.c' in graph.sources
        metadata=_LogMetadataDeclarations_Get(model,service.catalog,{})
        assert metadata['experimental_estimator']=={'plugin_id':identity,'schema_version':1,
            'hardware_tested':False,'flight_tested':False,'timing_qualified':False}
        # An explicitly saved old build flag remains untouched; compile access
        # is experimental, not a claim that runtime initialization is valid.
        model.algorithm_parameters[identity]['software_validation_build']=0
        old=Project_Validate(model,service.catalog)
        assert old.valid and model.algorithm_parameters[identity]['software_validation_build']==0
        assert any(row.code=='TIMING_PROFILE_UNQUALIFIED' and row.level=='warning' for row in old.issues)
    finally:
        window.close();qapp.processEvents()
