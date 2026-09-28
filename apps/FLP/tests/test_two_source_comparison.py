from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.charts import FlightPage
from silverstar_flp.ui.pages.replay import ReplayPage
from tests.sslog_synthetic import AnalysisFlight_Build


def _Recorded_Copy(series: TimeSeries, offset: float) -> TimeSeries:
    values = np.asarray(series.values, dtype=np.float64).copy()
    if values.shape[1] == 4:
        offset = 0.0
    values += offset
    return replace(series, values=values)


def test_recorded_kf6_is_single_baseline_for_kf6_and_pure_ins(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "comparison.BIN"))
    pure = PureInsAlgorithmPlugin().run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    recorded = {
        "kf6.recorded.navigation.position_enu": _Recorded_Copy(
            pure.channels["navigation.position_enu"], 2.0
        ),
        "kf6.recorded.navigation.velocity_enu": _Recorded_Copy(
            pure.channels["navigation.velocity_enu"], .2
        ),
        "kf6.recorded.attitude.q_nb": _Recorded_Copy(
            pure.channels["attitude.q_nb"], 0.0
        ),
    }
    dataset = replace(dataset, series={**dataset.series, **recorded})
    kf6 = replace(pure, algorithm_id="silverstar.algorithm.kf6")
    store = ReplayResultStore()
    pure_entry = store.Result_Add(pure, algorithm_name="Pure INS")
    kf_entry = store.Result_Add(kf6, algorithm_name="KF6")
    replay = ReplayPage(Translator("en_US"), builtin_registry())
    replay.Dataset_Set(dataset, store)
    replay.Result_Set(kf_entry)
    assert replay.comparison_table.rowCount() == 3
    assert replay.comparison_table.item(0, 0).text() == "Attitude"
    replay.Result_Set(pure_entry)
    assert replay.comparison_table.rowCount() == 3
    assert float(replay.comparison_table.item(2, 2).text().split()[0]) > 0

    flight = FlightPage(Translator("en_US"))
    resolver = ChannelResolver(dataset, store)
    flight.Dataset_Set(dataset, resolver)
    flight.show()
    app.processEvents()
    assert len(flight.position_plot.listDataItems()) == 3
    assert len(flight.velocity_plot.listDataItems()) == 3
    for entry in (kf_entry, pure_entry):
        assert store.ActiveSource_Set(entry.source_id)
        flight.Dataset_Set(dataset, resolver)
        app.processEvents()
        for plot, expected in ((flight.position_plot, 6),
                               (flight.velocity_plot, 6),
                               (flight.quaternion_plot, 8),
                               (flight.euler_plot, 6)):
            traces = plot.listDataItems()
            assert len(traces) == expected
            midpoint = expected // 2
            assert all(item.opts["pen"].style() == Qt.PenStyle.DashLine
                       for item in traces[:midpoint])
            assert all(item.opts["pen"].style() == Qt.PenStyle.SolidLine
                       for item in traces[midpoint:])
        names = [item.name() for item in flight.position_plot.listDataItems()]
        assert sum("Recorded" in name for name in names) == 3
    flight.close()
    replay.close()


def test_replay_mechanization_summary_shows_pass_and_only_first_failure(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "verification.BIN"))
    pure = PureInsAlgorithmPlugin().run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    verification = {
        "recorded_count": 3, "computed_count": 3,
        "intervals": ({"passed": True}, {"passed": True}, {"passed": True}),
        "passed": True, "first_divergence": None,
    }
    result = replace(pure, algorithm_id="silverstar.algorithm.kf6",
                     diagnostics={"mechanization_verification": verification})
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset, ReplayResultStore())
    page.Result_Set(result)
    app.processEvents()
    text = page.result_information_label.text()
    assert "Inertial frontend verification: PASS" in text
    assert "Matched: 3" in text and "First divergence: None" in text
    first = {
        "timestamp_us": 123, "source_sequence": 4,
        "delta_theta_difference": [1e-3, 0, 0],
        "delta_velocity_difference": [0, 1e-2, 0],
        "dt_difference_s": 1e-4,
        "start_timestamp_difference_us": 2,
        "end_timestamp_difference_us": 0,
    }
    failure = {**verification, "passed": False, "first_divergence": first,
               "intervals": ({"passed": True}, {"passed": False}, {"passed": False})}
    result = replace(result, diagnostics={"mechanization_verification": failure})
    page.Result_Set(result)
    text = page.result_information_label.text()
    assert "Inertial frontend verification: FAIL" in text
    assert "t=123 us" in text and "source sequence=4" in text
    assert "Matched: 1" in text
    page.close()
