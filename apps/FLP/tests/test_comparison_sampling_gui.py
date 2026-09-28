import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.ui.pages.charts import FlightPage
from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
from tests.sslog_synthetic import AnalysisFlight_Build


def test_kf_display_curves_overlay_recorded_and_selected_with_full_source(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC_sampling.BIN"))
    result = Kf6AlgorithmPlugin().run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    full = result.channels["navigation.position_enu"]
    store = ReplayResultStore()
    entry = store.Result_Add(result)
    assert store.ActiveSource_Set(entry.source_id)
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, ChannelResolver(dataset, store))
    app.processEvents()
    for plot in (page.position_plot, page.velocity_plot):
        curves = plot.listDataItems()
        recorded = curves[:3]
        active = curves[3:]
        assert len(curves) == 6
        assert len(recorded) == len(active) == 3
        assert all(curve.name().startswith("Recorded") for curve in recorded)
        assert all(curve.opts['pen'].style() == Qt.PenStyle.DashLine for curve in recorded)
        for curve in active:
            assert curve.opts['pen'].style() == Qt.PenStyle.SolidLine
            assert curve.opts['pen'].widthF() == 1.7
            assert curve.opts['symbol'] is None
        assert all('Recomputed' in curve.name() for curve in active)
    assert page._position is full
    explorer = DataExplorerPage(Translator("en_US"))
    explorer.Dataset_Set(dataset, store)
    for language in ("en_US", "zh_CN"):
        explorer.Language_Apply(Translator(language))
        explorer._Channel_Show(explorer.channel_list.currentItem())
        text = explorer.channel_metadata.text()
        assert ("Measured rate" if language == "en_US" else "实测频率") in text
        assert ("Median period" if language == "en_US" else "中位采样周期") in text
    page.close()
    explorer.close()
