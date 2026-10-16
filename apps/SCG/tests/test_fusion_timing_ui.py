import pytest

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.fusion_timing_editor import FusionTimingEditor
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage


@pytest.mark.parametrize("kind", ["kf6", "eskf15", "sf6"])
@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_only_implemented_modes_have_named_common_selector(builtin_catalog, qapp, kind, language):
    owner = builtin_catalog.Component_Get("silverstar.algorithm.estimator." + kind)
    values = {owner.component_id: {p.parameter_id: p.default for p in owner.algorithm_parameters}}
    page = NavigationConfigurationPage(Translator(language))
    page.Configuration_Set((owner,), values)
    page.show()
    qapp.processEvents()
    key = (owner.component_id, "fusion_timing_mode")
    if kind == "sf6":
        assert key not in page.editors
    else:
        editor = page.editors[key]
        assert isinstance(editor, FusionTimingEditor)
        assert editor.isVisible() and editor.count() == 3 and editor.value() == 1
        assert [editor.itemData(i) for i in range(3)] == [0, 1, 2]
        assert all(editor.itemText(i) for i in range(3))
        changes = []
        page.parameterChanged.connect(lambda *args: changes.append(args))
        editor.setValue(2)
        assert changes == []
        editor.activated.emit(2)
        qapp.processEvents()  # Page commits use its existing queued signal boundary.
        assert changes == [(owner.component_id, "fusion_timing_mode", 2)]
    page.close()
