from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.artifact_memory import ArtifactMemorySummary_Decode, ArtifactMemorySummary_Encode
from silverstar_fccg.project.quality_results import QualityResultRecord
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.pages.build import BuildPage
from silverstar_fccg.ui.theme import Theme_Apply

import pytest


OUTPUT = """FLASH used=299556 remaining=224732 capacity=524288
main SRAM used=99880 remaining=31192 capacity=131072
CCMRAM used=64296 remaining=1240 capacity=65536
"""


@pytest.mark.parametrize("language", ("en_US", "zh_CN"))
def test_actual_resource_occupancy_keeps_narrow_margin_warning_and_retranslates(qapp, language):
    translator = Translator(language)
    page = BuildPage(translator)
    page.show()
    summary = MainWindow._QualitySummary_Get(BuildResult(BuildAction.ARTIFACT_CHECK, (), 0, OUTPUT))
    record = QualityResultRecord("artifact_check", "passed", "2026-10-01T00:00:00Z", 1.0, summary)
    page.QualityResults_Set((record,))
    text = page.memory_margin_value.text()
    assert "64,296" in text and "1,240" in text and "65,536" in text
    assert page.memory_margin_value.property("statusLevel") == "error"
    assert translator.Text_Get("memory.ccm_narrow") in text
    assert page.memory_margin_value.isVisible()
    other = Translator("zh_CN" if language == "en_US" else "en_US")
    page.Language_Apply(other)
    assert other.Text_Get("memory.ccm_narrow") in page.memory_margin_value.text()


def test_failed_artifact_retains_usage_without_claiming_verified(qapp):
    page = BuildPage(Translator("en_US"))
    summary = MainWindow._QualitySummary_Get(BuildResult(BuildAction.ARTIFACT_CHECK, (), 2, OUTPUT))
    page.QualityResults_Set((QualityResultRecord("artifact_check", "failed", "", 0, summary),))
    assert "1,240" in page.memory_margin_value.text()
    assert "verified" not in page.quality_result_labels["artifact_check"].text().lower()
    page.QualityResults_Set(())
    assert "1,240" not in page.memory_margin_value.text()


def test_memory_status_repaints_for_dark_theme_without_losing_usage(qapp):
    page = BuildPage(Translator("en_US"))
    summary = MainWindow._QualitySummary_Get(BuildResult(BuildAction.ARTIFACT_CHECK, (), 0, OUTPUT))
    record = QualityResultRecord("artifact_check", "passed", "", 0, summary)
    try:
        Theme_Apply(qapp, "light")
        page.QualityResults_Set((record,))
        light = page.memory_margin_value.text()
        Theme_Apply(qapp, "dark")
        page.QualityResults_Set((record,))
        dark = page.memory_margin_value.text()
        assert light != dark
        assert "1,240" in dark and "64,296" in dark
        assert page.memory_margin_value.property("statusLevel") == "error"
        Theme_Apply(qapp, "light")
        page.QualityResults_Set((record,))
        assert page.memory_margin_value.text() == light
    finally:
        Theme_Apply(qapp, "light")
        page.close()


@pytest.mark.parametrize("output", ("", OUTPUT+OUTPUT, OUTPUT.replace("remaining=1240", "remaining=1200")))
def test_malformed_or_ambiguous_resource_output_cannot_create_margin(output):
    assert ArtifactMemorySummary_Encode(output) == ""
    assert ArtifactMemorySummary_Decode("artifact_memory=1/2/3") == ()
