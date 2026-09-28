from types import SimpleNamespace

import numpy as np

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import InertialIncrement


def test_measurement_availability_precedes_decimated_snapshot_and_updates_once(monkeypatch):
    increments = tuple(
        InertialIncrement(
            t - 10000,
            t,
            i,
            i,
            np.float32(0.01),
            np.zeros(3, dtype=np.float32),
            np.zeros(3, dtype=np.float32),
        )
        for i, t in enumerate((10000, 20000, 30000, 40000))
    )

    def record(kind, sequence, sample, receive):
        return DecodedRecord(
            1,
            kind,
            1,
            0,
            sequence,
            sample,
            0,
            {"sequence": sequence, "sample_timestamp_us": sample, "receive_timestamp_us": receive},
            0,
        )

    baro = tuple(
        record("BARO_MEASUREMENT", i, sample, receive)
        for i, (sample, receive) in enumerate(
            ((13000, 13000), (20000, 20000), (21000, 31000), (50000, 50000)), 1
        )
    )
    gnss = (record("GNSS_MEASUREMENT", 5, 12000, 19000),)
    snapshot = DecodedRecord(
        1, "ESTIMATOR", 1, 0, 10, 40000, 0, {"gnss_sequence": 5, "baro_sequence": 1}, 0
    )
    records = {"BARO_MEASUREMENT": baro, "GNSS_MEASUREMENT": gnss, "ESTIMATOR": (snapshot,)}
    dataset = SimpleNamespace(Records_Get=lambda kind: records.get(kind, ()))
    plugin = Kf6AlgorithmPlugin()
    schedule, inferred = plugin._MeasurementSchedule_Build(dataset, increments)
    assert inferred
    assert [
        (m.kind, m.record.payload["sequence"], m.application_timestamp_us) for m in schedule
    ] == [("gnss", 5, 20000), ("baro", 1, 20000), ("baro", 2, 20000), ("baro", 3, 40000)]
    events = []
    original_predict = Kf6Filter.Kf6_Predict

    def predict(self, delta, dt):
        events.append("predict")
        return original_predict(self, delta, dt)

    def gnss_apply(instance, measurement):
        events.append(("gnss", measurement.payload["sequence"]))
        return 0, 0, 0, np.ones(2, dtype=np.float32)

    def baro_apply(instance, measurement):
        events.append(("baro", measurement.payload["sequence"]))
        return 0, 1.0, 0

    monkeypatch.setattr(Kf6Filter, "Kf6_Predict", predict)
    monkeypatch.setattr(plugin, "_Gnss_Apply", gnss_apply)
    monkeypatch.setattr(plugin, "_Baro_Apply", baro_apply)
    filter_instance = Kf6Filter(np.ones(3), np.ones(3), np.ones(3) * 10, np.float32(10))
    context = SimpleNamespace(
        Cancel_RaiseIfRequested=lambda: None, Progress_Report=lambda *args: None
    )
    output = plugin._Replay_Run(
        filter_instance,
        np.array([1.0, 0.0, 0.0, 0.0]),
        increments,
        schedule,
        {"gravity_mps2": 9.78},
        context,
    )
    assert events == [
        "predict",
        "predict",
        ("gnss", 5),
        ("baro", 1),
        ("baro", 2),
        "predict",
        "predict",
        ("baro", 3),
    ]
    assert [s.timestamp_us for s in output] == [10000, 20000, 30000, 40000]
    assert plugin._MeasurementSchedule_Build(dataset, ()) == ((), False)


def test_target_tables_keep_last_column_stretched_after_refresh(tmp_path):
    from PySide6.QtWidgets import QApplication, QHeaderView

    from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
    from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
    from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
    from silverstar_flp.ui.pages.replay import ReplayPage
    from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
    from tests.sslog_synthetic import AnalysisFlight_Build

    app = QApplication.instance() or QApplication([])
    data = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC_tables.BIN"))
    result = PureInsAlgorithmPlugin().run(data, ReplayRequest(mode=ReplayMode.OFFLINE))
    replay = ReplayPage(Translator(), builtin_registry())
    explorer = DataExplorerPage(Translator())
    state = StateEstimationPage(Translator())
    for page in (replay, explorer):
        page.Dataset_Set(data, ReplayResultStore())
    state.Dataset_Set(data, ChannelResolver(data, ReplayResultStore()))
    for _ in range(4):
        replay._Comparison_Set(result)
        explorer._Channel_Show(explorer.channel_list.currentItem())
        explorer._Records_Show()
        for table in (
            replay.comparison_table,
            explorer.channel_table,
            explorer.record_table,
            state.nis_summary,
        ):
            table.setParent(None)
            table.resize(2400, 200)
            table.show()
            app.processEvents()
            header = table.horizontalHeader()
            last = table.columnCount() - 1
            assert last >= 0
            assert header.sectionResizeMode(last) == QHeaderView.ResizeMode.Stretch
            if table is not state.nis_summary:
                assert all(
                    header.sectionResizeMode(i) == QHeaderView.ResizeMode.ResizeToContents
                    for i in range(last)
                )
            if table.horizontalScrollBar().maximum() == 0:
                assert (
                    abs(
                        header.sectionViewportPosition(last)
                        + header.sectionSize(last)
                        - table.viewport().width()
                    )
                    <= 2
                )
            table.hide()
    for page in (replay, explorer, state):
        page.close()
