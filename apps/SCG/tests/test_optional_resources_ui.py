from copy import deepcopy

import pytest
from PySide6.QtWidgets import QMessageBox
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from uuid import uuid4


@pytest.fixture
def window(qapp, workspace_root, tmp_path):
    # The application's path policy deliberately rejects settings outside SCG.
    settings = workspace_root/'.work/dev013_gshc_accept24_ui01'/uuid4().hex/'scg.ini'
    current = MainWindow(SettingsStore(settings), service=FccgService(workspace_root))
    current._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    yield current
    current.close()
    qapp.processEvents()


def test_resource_checkboxes_commit_refresh_and_tier_restore(window):
    page = window.devices_page
    original_protocols = deepcopy(window._model.protocols)
    page.maintenance_log_export_enabled.setChecked(False)
    assert not window._model.build.maintenance_log_export_enabled
    assert window._model.protocols == original_protocols
    page.magnetometer_enabled.setChecked(False)
    assert not window._model.build.magnetometer_enabled
    window._Project_Refresh()
    assert not page.magnetometer_enabled.isChecked()
    for tier in ('compact', 'minimal'):
        window._FeatureTier_Change(tier)
        assert not page.magnetometer_enabled.isEnabled()
        assert not page.maintenance_log_export_enabled.isEnabled()
        assert not page.magnetometer_enabled.isChecked()
        assert not page.maintenance_log_export_enabled.isChecked()
    window._FeatureTier_Change('full')
    assert page.magnetometer_enabled.isEnabled()
    assert page.maintenance_log_export_enabled.isEnabled()
    assert not page.magnetometer_enabled.isChecked()
    assert not page.maintenance_log_export_enabled.isChecked()
    assert window._model.protocols == original_protocols
