from pathlib import Path

import pytest

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.validation import ValidationIssue
from silverstar_fccg.ui.main_window import MainWindow


@pytest.mark.parametrize("code,page_code", (
    ("board_unselected", "page.board_hardware"),
    ("GROUND_BOARD_UNSELECTED", "page.ground"),
    ("GROUND_PC_INTERFACE_UNBOUND", "page.ground_configuration"),
    ("STORAGE_DEVICE_REQUIRED", "page.devices"),
    ("STORAGE_SDIO_UNBOUND", "page.board_hardware"),
    ("unknown_contract_error", "page.build"),
))
def test_validation_focus_follows_actual_editor_owner(tmp_path: Path, qapp, code, page_code):
    window = MainWindow(SettingsStore(tmp_path / "routing.ini"))
    try:
        before = window._model.Dictionary_Get()
        window._ValidationIssue_Navigate((ValidationIssue("error", code, "fixture"),))
        index = window.PAGE_CODES.index(page_code)
        page = window._page_widgets[index]
        assert window.navigation_list.currentRow() == index
        assert window.pages.currentWidget() is page
        target = window._validation_focus_widget
        assert page is target or page.isAncestorOf(target)
        assert target.property("validationIssue") is True
        assert window._model.Dictionary_Get() == before
        window._ValidationIssue_Clear()
        assert target.property("validationIssue") is False
    finally:
        window.close()
