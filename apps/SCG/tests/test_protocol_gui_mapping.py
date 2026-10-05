from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtTest import QSignalSpy

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import StandardComboBox


@pytest.mark.parametrize("category", ["telemetry", "maintenance", "logging"])
@pytest.mark.parametrize("container", [tuple, list])
def test_protocol_selection_restores_without_qvariant_equality(
    tmp_path, qapp, monkeypatch, category, container,
):
    original = StandardComboBox.itemData
    original_find = StandardComboBox.findData

    def find_data(self, value, *args):
        # Simulate the reported Qt/QVariant lookup miss without changing the model.
        if self.objectName().startswith("protocolProfile_"):
            return -1
        return original_find(self, value, *args)

    monkeypatch.setattr(StandardComboBox, "findData", find_data)

    def item_data(self, index, *args):
        value = original(self, index, *args)
        return container(value) if isinstance(value, (tuple, list)) else value

    monkeypatch.setattr(StandardComboBox, "itemData", item_data)
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"))
    try:
        before = deepcopy(window._model)
        selection = before.protocols[category]
        assert selection is not None
        spy = QSignalSpy(window.flight_configuration_page.protocolProfileChanged)
        window._Project_Refresh()
        combo = window.flight_configuration_page.protocol_combos[category]
        assert combo.currentIndex() > 0
        assert tuple(combo.itemData(combo.currentIndex())) == (selection.component, selection.profile)
        assert window._model == before
        assert spy.count() == 0
    finally:
        window.close()


def test_missing_protocol_is_distinct_from_no_selection_and_refresh_is_read_only(tmp_path, qapp):
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"))
    try:
        page = window.flight_configuration_page
        before = deepcopy(window._model)
        selections = dict(page._selected_protocol_profiles)
        spy = QSignalSpy(page.protocolProfileChanged)
        page.Protocols_Set({}, selections)
        for category, selection in selections.items():
            assert selection is not None
            combo = page.protocol_combos[category]
            assert combo.currentIndex() > 0
            assert not combo.model().item(combo.currentIndex()).isEnabled()
            assert combo.toolTip()
            assert combo.currentText() != combo.itemText(0)
        assert window._model == before
        assert spy.count() == 0
        page.Protocols_Set({}, dict.fromkeys(selections))
        assert all(combo.currentIndex() == 0 and combo.currentData() is None
                   for combo in page.protocol_combos.values())
        assert window._model == before
        assert spy.count() == 0
    finally:
        window.close()


@pytest.mark.parametrize("category", ["telemetry", "maintenance", "logging"])
def test_unselected_model_remains_unselected(tmp_path, qapp, category):
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"))
    try:
        window._model.protocols[category] = None
        before = deepcopy(window._model)
        window._Project_Refresh()
        combo = window.flight_configuration_page.protocol_combos[category]
        assert combo.currentIndex() == 0
        assert combo.currentData() is None
        assert not combo.property("validationIssue")
        assert window._model == before
    finally:
        window.close()
