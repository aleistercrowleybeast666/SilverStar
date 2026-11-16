"""The endpoint display must reflect the private draft after every PHY edit."""
from copy import deepcopy
from dataclasses import replace

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.radio_transaction import RadioTransaction_EndpointSet
from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog


def test_clearing_one_invalid_endpoint_keeps_peer_visible(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('visible radio draft')
    model = RadioTransaction_EndpointSet(model, service.catalog, 'ground',
        'silverstar.device.telemetry.sx1281', 'e28_2g4m12sx', 12)
    before = deepcopy(model.Dictionary_Get())
    dialog = RadioTransactionDialog(Translator('en_US'), model, service.catalog)
    dialog.editor.fields['frequency_hz'].committed.emit(100.0)
    flight = dialog.endpoints['flight'][0]
    ground = dialog.endpoints['ground'][0]
    flight.setCurrentIndex(0)
    expected = ('silverstar.device.telemetry.sx1281', 'e28_2g4m12sx')
    assert ground.currentData() is not None and tuple(ground.currentData()) == expected
    assert not ground.model().item(ground.currentIndex()).isEnabled()
    assert dialog._draft.ground_target.radio_plugin == expected[0]
    dialog.defaults_button.click()
    assert ground.currentData() is not None and tuple(ground.currentData()) == expected
    assert ground.model().item(ground.currentIndex()).isEnabled()
    assert ground.count() > 2
    assert flight.currentData() is None
    dialog.accept()
    result = dialog.Configuration_Get()
    assert result is not None and result.ground_target.module_variant == expected[1]
    assert result.DeviceInstance_Get(result.air_link.flight_radio_instance) is None
    assert model.Dictionary_Get() == before


@pytest.mark.parametrize('restore', [False, True])
def test_correcting_imported_invalid_phy_restores_candidates(qapp, workspace_root, restore):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('invalid imported PHY')
    model.air_link = replace(model.air_link, frequency_hz=100_000_000)
    before = deepcopy(model.Dictionary_Get())
    dialog = RadioTransactionDialog(Translator('en_US'), model, service.catalog)
    combo = dialog.endpoints['flight'][0]
    selected = combo.currentData()
    assert selected is not None
    assert not combo.model().item(combo.currentIndex()).isEnabled()
    if restore:
        dialog.defaults_button.click()
    else:
        dialog.editor.fields['frequency_hz'].committed.emit(2473.0)
    assert combo.currentData() == selected
    assert combo.model().item(combo.currentIndex()).isEnabled()
    assert combo.count() > 2
    assert all(combo.itemData(index)[0] == selected[0] for index in range(1, combo.count()))
    dialog.reject()
    assert dialog.Configuration_Get() is None and model.Dictionary_Get() == before
