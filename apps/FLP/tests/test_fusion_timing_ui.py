import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.fusion_timing_editor import FusionTimingEditor
from silverstar_flp.ui.pages.replay import ReplayPage


@pytest.mark.parametrize("algorithm", ["silverstar.algorithm.kf6", "silverstar.algorithm.estimator.eskf15"])
@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_actual_parameter_schema_drives_two_named_modes(algorithm, language):
    app = QApplication.instance() or QApplication([])
    page = ReplayPage(Translator(language), builtin_registry())
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData(algorithm))
    page.show()
    app.processEvents()
    editor = page._parameter_widgets["fusion_timing_mode"]
    assert isinstance(editor, FusionTimingEditor)
    assert editor.count() == 2 and editor.isVisible() and editor.value() == 1
    assert [editor.itemData(i) for i in range(2)] == [0, 1]
    assert page._CommonParameter_Is(page._parameter_specs["fusion_timing_mode"])
    editor.setValue(0)
    editor.Language_Set("en_US" if language == "zh_CN" else "zh_CN")
    assert editor.value() == 0
    editor.setReadOnly(True)
    assert not editor.isEnabled()
    assert "fusion_timing_mode" not in page._recorded_parameter_values
    page.close()
    page.deleteLater()
    app.processEvents()
