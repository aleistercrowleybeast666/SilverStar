from copy import deepcopy
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QDialog

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.radio_transaction import (
    RadioTransaction_Commit, RadioTransaction_EndpointSet, RadioTransaction_IssuesGet)
from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog
from test_three_workspace_workflow import workspace_window
from test_mission_phase_gui import _Modal_Click


def test_pair_change_is_private_and_final_phy_is_checked(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('radio pair')
    before = deepcopy(model.Dictionary_Get())
    draft = RadioTransaction_EndpointSet(model, service.catalog, 'flight',
        'silverstar.device.telemetry.sx1278', 'e32_400m20s', 17)
    assert RadioTransaction_IssuesGet(draft, service.catalog)
    with pytest.raises(ValueError, match='AIR_LINK'):
        RadioTransaction_Commit(draft, service.catalog)
    draft = RadioTransaction_EndpointSet(draft, service.catalog, 'ground',
        'silverstar.device.telemetry.sx1278', 'e32_400m20s', 17)
    draft.air_link = replace(draft.air_link, radio_family='sx127x', frequency_hz=433000000,
                            spreading_factor=7, bandwidth_hz=125000)
    result = RadioTransaction_Commit(draft, service.catalog)
    assert result.air_link.radio_family == 'sx127x'
    assert result.DeviceInstance_Get(result.air_link.flight_radio_instance).plugin.endswith('sx1278')
    assert result.ground_target.radio_plugin.endswith('sx1278')
    assert model.Dictionary_Get() == before


def test_configured_peer_conflict_visible_but_absent_peer_allowed(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('one target')
    assert not RadioTransaction_IssuesGet(model, service.catalog)
    draft = RadioTransaction_EndpointSet(model, service.catalog, 'ground',
        'silverstar.device.telemetry.sx1278', 'e32_400m20s', 17)
    assert any(issue.code == 'AIR_LINK_FAMILY_MISMATCH'
               for issue in RadioTransaction_IssuesGet(draft, service.catalog))


def test_dialog_cancel_and_pair_apply_are_atomic(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('radio dialog')
    before = deepcopy(model.Dictionary_Get())
    for cancel in (True, False):
        dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
        dialog.show()
        for endpoint in ('flight', 'ground'):
            combo = dialog.endpoints[endpoint][0]
            index = combo.findData(('silverstar.device.telemetry.sx1278', 'e32_400m20s'))
            assert index >= 0 and combo.model().item(index).isEnabled()
            combo.setCurrentIndex(index)
        dialog.preset.setCurrentIndex(dialog.preset.findData('sx127x'))
        dialog._Preset_Apply()
        if cancel:
            dialog.reject()
            assert dialog.Configuration_Get() is None
        else:
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
            assert dialog.Configuration_Get().air_link.frequency_hz == 433000000
        assert model.Dictionary_Get() == before
        dialog.close()


def test_normal_shared_link_button_cancel_keeps_project(workspace_window, qapp):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('normal link entry')
    window._Project_Refresh()
    window.show()
    qapp.processEvents()
    before = deepcopy(window._model.Dictionary_Get())
    _Modal_Click(window.hardware_workspace.link_button, RadioTransactionDialog,
                 lambda dialog: dialog.reject())
    assert window._model.Dictionary_Get() == before
    assert not errors
