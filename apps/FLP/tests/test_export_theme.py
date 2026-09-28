from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportOptions, ExportTheme, FlightExporter
from silverstar_flp.ui.pages.export_settings import ExportDialog
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse


@pytest.mark.parametrize("ui_theme,mode,resolved", [
    ("light", ExportTheme.FOLLOW_UI, "light"),
    ("dark", ExportTheme.FOLLOW_UI, "dark"),
    ("dark", ExportTheme.LIGHT, "light"),
    ("light", ExportTheme.DARK, "dark"),
])
def test_export_theme_manifest_records_mode_and_resolved(tmp_path, ui_theme, mode, resolved):
    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "theme.bin"))
    manifest = FlightExporter().export(
        dataset, tmp_path / "output",
        options=ExportOptions(
            language="en_US", theme=mode, ui_theme=ui_theme,
            include_overview=False, include_diagnostics=False,
            include_events=False, include_csv=False,
            include_full_covariance_keyframes=False, include_plots=False,
            include_trajectory_3d=False, include_attitude_gif=False,
        ),
    )
    assert not manifest.failures
    data = json.loads((tmp_path / "output" / "Export_Manifest_EN.json").read_text())
    assert data["theme_mode"] == mode.value
    assert data["resolved_theme"] == resolved
    assert manifest.theme.value == resolved


def test_dialog_defaults_follow_ui_and_preserves_explicit_choice():
    app = QApplication.instance() or QApplication([])
    assert app is not None
    dialog = ExportDialog(Translator("en_US"))
    assert dialog.export_theme_combo.currentData() == "follow_ui"
    dialog.export_theme_combo.setCurrentIndex(dialog.export_theme_combo.findData("light"))
    dialog.Language_Apply(Translator("zh_CN"))
    assert dialog.export_theme_combo.currentData() == "light"
    dialog.close()
