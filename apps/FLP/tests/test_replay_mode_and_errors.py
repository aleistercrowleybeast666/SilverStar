"""Tiny GUI contracts for explicit modes and retained evidence-error explanations."""

import pytest
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import ReplayMode
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.replay import ReplayPage

from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_replay_lifecycle_boundaries import tiny_dataset, tiny_result


def Page_Build(qtbot, dataset):
    page = ReplayPage(Translator("en_US"), builtin_registry())
    qtbot.addWidget(page)
    page.Dataset_Set(dataset)
    return page


def Algorithm_Select(page, algorithm):
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData(algorithm))


def Mode_Select(page, mode):
    index = page.mode_combo.findData(mode)
    page.mode_combo.setCurrentIndex(index)
    page.mode_combo.activated.emit(index)


def test_automatic_eskf_fallback_does_not_change_kf6_default(qtbot, tmp_path):
    page = Page_Build(qtbot, NavigationPair_Open(tmp_path / "input").dataset)
    Algorithm_Select(page, "silverstar.algorithm.kf6")
    assert page._Request_Get().mode == ReplayMode.RECORDED_CONFIGURATION
    Algorithm_Select(page, "silverstar.algorithm.estimator.eskf15")
    assert page._Request_Get().mode == ReplayMode.OFFLINE
    Algorithm_Select(page, "silverstar.algorithm.kf6")
    assert page._Request_Get().mode == ReplayMode.RECORDED_CONFIGURATION
    assert page._mode_preferences == {}


@pytest.mark.parametrize("mode", [ReplayMode.OFFLINE, ReplayMode.WHAT_IF])
def test_user_selected_kf6_mode_survives_algorithm_and_language_changes(qtbot, tmp_path, mode):
    page = Page_Build(qtbot, NavigationPair_Open(tmp_path / "input").dataset)
    Algorithm_Select(page, "silverstar.algorithm.kf6")
    Mode_Select(page, mode)
    Algorithm_Select(page, "silverstar.algorithm.estimator.eskf15")
    Algorithm_Select(page, "silverstar.algorithm.kf6")
    page.Language_Apply(Translator("zh_CN"))
    assert page.mode_combo.currentData() == mode
    assert page._Request_Get().mode == mode
    assert page.Configuration_Get()["mode"] == mode.value


def test_missing_recorded_configuration_falls_back_without_erasing_preference(qtbot, tmp_path):
    dataset = NavigationPair_Open(tmp_path / "input").dataset
    page = Page_Build(qtbot, dataset)
    Algorithm_Select(page, "silverstar.algorithm.kf6")
    Mode_Select(page, ReplayMode.RECORDED_CONFIGURATION)
    page.Dataset_Set(tiny_dataset("old-log"))
    assert page.mode_combo.currentData() == ReplayMode.OFFLINE
    assert page._mode_preferences["silverstar.algorithm.kf6"] == ReplayMode.RECORDED_CONFIGURATION
    page.Dataset_Set(dataset)
    assert page._Request_Get().mode == ReplayMode.RECORDED_CONFIGURATION


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_detailed_initialization_error_is_visible_localized_and_retranslated(qtbot, language):
    page = Page_Build(qtbot, tiny_dataset("missing-evidence"))
    page.Language_Apply(Translator(language))
    error = "parameter_dynamic_uncertainty_missing:GNSS_initialization"
    page.Result_Error(error)
    text = page.result_label.text()
    assert text.startswith(
        page._translator.Text_Get("error.code.parameter_dynamic_uncertainty_missing")
    )
    assert "START" in text and "GNSS" in text
    assert page.result_label.toolTip() == error
    assert "GNSS_initialization" not in text
    other = "en_US" if language == "zh_CN" else "zh_CN"
    page.Language_Apply(Translator(other))
    assert page.result_label.text() != text
    assert "START" in page.result_label.text()
    page.Result_Set(tiny_result())
    assert page._last_error is None and page.result_label.toolTip() == ""


def test_unknown_error_detail_is_preserved(qtbot):
    page = Page_Build(qtbot, tiny_dataset("unknown"))
    page.Result_Error("unknown_error:first:second")
    assert page.result_label.text() == "unknown_error:first:second"
    page.Result_Error("parameter_dynamic_uncertainty_missing:future_detail")
    assert page.result_label.text().endswith("future_detail")
