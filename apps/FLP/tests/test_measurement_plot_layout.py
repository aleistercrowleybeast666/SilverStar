from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.parameter_fixtures import SyntheticParameters_Attach
from tests.sslog_synthetic import AnalysisFlight_Build


def _Series(time, values, unit):
    values = np.asarray(values, dtype=np.float64)
    return TimeSeries(np.asarray(time, dtype=np.uint64), values, unit,
                      "measurement", "test", np.ones(len(time), dtype=bool))


@pytest.mark.parametrize("language", ("zh_CN", "en_US"))
@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("font_scale", (1, 2))
def test_sigma_timing_and_measurement_plot_alignment(
    tmp_path, language, theme, font_scale
):
    app = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "plot.BIN"))
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    start = dataset.start_timestamp_us or 0
    time = [start + 100_000, start + 200_000, start + 300_000]
    series = {
        "kf6.recorded.measurement_input_variance.position_en": _Series(
            time, [[4, 9], [16, 25], [36, 49]], "m^2"
        ),
        "kf6.recorded.measurement_effective_variance.position_en": _Series(
            time, [[9, 16], [25, 36], [49, 64]], "m^2"
        ),
        "kf6.recorded.measurement_r_scale.position_en": _Series(
            time, [2.25, 1.5625, 1.3611], "1"
        ),
        "kf6.recorded.measurement_receive_age.position_en": _Series(
            time, [3, 4, 5], "ms"
        ),
        "kf6.recorded.measurement_fixed_lag_latency.position_en": _Series(
            time, [273, 274, 275], "ms"
        ),
    }
    dataset = replace(dataset, series={**dataset.series, **series})
    page = StateEstimationPage(Translator(language))
    font = page.font()
    font.setPointSize(max(8, font.pointSize() * font_scale))
    page.setFont(font)
    page.Theme_Apply(theme)
    page.Dataset_Set(dataset, ChannelResolver(dataset, ReplayResultStore()))
    page.measurement_group_combo.setCurrentIndex(
        page.measurement_group_combo.findData("gnss_position_en")
    )
    page.resize(1100, 900)
    page.show()
    app.processEvents()
    assert len(page.measurement_uncertainty_plot.listDataItems()) == 4
    curves = page.measurement_uncertainty_plot.listDataItems()
    np.testing.assert_allclose(curves[0].getData()[1], (2, 4, 6))
    np.testing.assert_allclose(curves[1].getData()[1], (3, 5, 7))
    np.testing.assert_allclose(curves[2].getData()[1], (3, 5, 7))
    np.testing.assert_allclose(curves[3].getData()[1], (4, 6, 8))
    assert len(page.measurement_age_plot.listDataItems()) == 2
    assert "ms" in page.measurement_age_plot.getAxis("left").labelText
    plots = (page.measurement_uncertainty_plot, page.measurement_age_plot)
    left_edges = [plot.getPlotItem().vb.sceneBoundingRect().left() for plot in plots]
    assert max(left_edges) - min(left_edges) <= 2.0
    page.measurement_age_plot.setXRange(.1, .2, padding=0)
    app.processEvents()
    ranges = [plot.getViewBox().viewRange()[0] for plot in plots]
    assert max(value[0] for value in ranges) - min(value[0] for value in ranges) < 1e-6
    assert max(value[1] for value in ranges) - min(value[1] for value in ranges) < 1e-6
    page.close()
