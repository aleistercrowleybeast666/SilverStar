"""Receiver-native GNSS consistency and receiver-information views."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.analysis.gnss_integrity_display import (
    HorizontalQuality_Build, HorizontalQualitySummary_Get, ReceiverInformation_Build,
)
from silverstar_flp.analysis.gnss_vertical_consistency import GnssVerticalConsistency_Build
from silverstar_flp.ui.plot_helpers import _Plot_Prepare, _Plot_Reset, _PlotViews_Reset
from silverstar_flp.ui.theme import Plot_Colors
from silverstar_flp.ui.widgets import StandardComboBox


class GnssIntegrityPage(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._theme = "light"
        self._dataset = None
        self._parameters = {}
        self._source_available = True
        self._result = None
        self._vertical = None
        self._window_evidence = None
        self._source_kind = "recorded"
        self._horizontal = None
        self._origin = 0
        self._interval = (0.0, float("inf"))
        layout = QVBoxLayout(self)
        selector = QHBoxLayout()
        self.display_label = QLabel()
        self.display_combo = StandardComboBox()
        self.display_combo.currentIndexChanged.connect(self._Display_Changed)
        selector.addWidget(self.display_label)
        selector.addWidget(self.display_combo)
        selector.addStretch(1)
        layout.addLayout(selector)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        horizontal_page = QWidget()
        horizontal_layout = QVBoxLayout(horizontal_page)
        self.horizontal_note = QLabel()
        self.horizontal_note.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        horizontal_layout.addWidget(self.horizontal_note)
        horizontal_layout.addWidget(self.status_label)
        self.closure_plot = pg.PlotWidget()
        horizontal_layout.addWidget(self.closure_plot, 1)
        self.weight_plot = pg.PlotWidget()
        self.weight_plot.setXLink(self.closure_plot)
        horizontal_layout.addWidget(self.weight_plot, 1)
        self.pages.addWidget(horizontal_page)

        vertical_page = QWidget()
        vertical_layout = QVBoxLayout(vertical_page)
        self.vertical_note = QLabel()
        self.vertical_note.setWordWrap(True)
        vertical_layout.addWidget(self.vertical_note)
        self.vertical_plot = pg.PlotWidget()
        vertical_layout.addWidget(self.vertical_plot, 1)
        self.pages.addWidget(vertical_page)

        information_page = QWidget()
        information_layout = QVBoxLayout(information_page)
        self.quality_plot = pg.PlotWidget()
        self.satellite_plot = pg.PlotWidget()
        self.quality_plot.showAxis("right")
        self._speed_view = pg.ViewBox()
        # The secondary ViewBox has its own popup outside PlotWidget's menus.
        # Bind its native lifetime to the GUI plot as well.
        speed_menu = self._speed_view.menu
        if speed_menu is not None:
            speed_menu.setParent(self.quality_plot, speed_menu.windowFlags())
        self.quality_plot.scene().addItem(self._speed_view)
        self.quality_plot.getAxis("right").linkToView(self._speed_view)
        self._speed_view.setXLink(self.quality_plot)
        self.quality_plot.getViewBox().sigResized.connect(self._SpeedView_Align)
        self.satellite_plot.setXLink(self.quality_plot)
        self.quality_plot.getAxis("left").setWidth(68)
        self.satellite_plot.getAxis("left").setWidth(68)
        information_layout.addWidget(self.quality_plot, 1)
        information_layout.addWidget(self.satellite_plot, 1)
        self.pages.addWidget(information_page)
        self.plots = (self.closure_plot, self.weight_plot, self.vertical_plot,
                      self.quality_plot, self.satellite_plot)
        for plot in self.plots:
            plot.addLegend()
            _Plot_Prepare(plot, self._theme)
        self.Language_Apply(translator)

    def _SpeedView_Align(self):
        self._speed_view.setGeometry(self.quality_plot.getViewBox().sceneBoundingRect())
        self._speed_view.linkedViewChanged(
            self.quality_plot.getViewBox(),
            self._speed_view.XAxis,
        )

    def _Display_Changed(self, index):
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def Dataset_Set(self, dataset):
        self._dataset = dataset
        self._window_evidence = None
        self._source_kind = "recorded"
        self._origin = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        self._Rebuild()

    def SourceUnavailable_Set(self):
        self._parameters = {}
        self._source_available = False
        self._window_evidence = None
        self._horizontal = None
        self._result = None
        self._vertical = None
        _Plot_Reset(self.plots)
        self._speed_view.clear()
        self.horizontal_note.setText(self._translator.Text_Get("state.selected_no_estimator"))
        self.vertical_note.setText(self._translator.Text_Get("state.selected_no_estimator"))
        self.status_label.clear()

    def Parameters_Set(self, parameters):
        self._source_available = True
        self._parameters = dict(parameters or {})
        self._Rebuild()

    def Source_Set(self, parameters, *, source_kind, window_evidence=None):
        self._source_available = True
        self._parameters = dict(parameters or {})
        self._source_kind = source_kind
        self._window_evidence = window_evidence
        self._Rebuild()

    def WindowEvidence_Set(self, evidence):
        self._source_kind = "recomputed"
        self._window_evidence = evidence
        self._Rebuild()

    def _WindowEvidence_Render(self):
        trace = self._horizontal
        if trace is None:
            return
        label = self._translator.Text_Get
        for plot in (self.closure_plot, self.weight_plot):
            _Plot_Reset((plot,))
        time = (trace.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        for plot, values, key, color in (
            (self.closure_plot, trace.closure_norm_m, "integrity.window_error", "#2b77c2"),
            (self.weight_plot, trace.variance_scale, "integrity.window_scale", "#1a9d6c"),
        ):
            style = ({"pen": pg.mkPen(color, width=1.5), "stepMode": "right"}
                     if trace.source_kind == "recorded" else
                     {"pen": None, "symbol": "o", "symbolSize": 5,
                      "symbolBrush": color, "symbolPen": color})
            plot.plot(time, values, connect="finite", name=label(key), **style)
        threshold = self._parameters.get("gnss_integrity_error_threshold_m")
        if threshold is not None and np.isfinite(float(threshold)):
            self.closure_plot.addItem(pg.InfiniteLine(
                pos=float(threshold), angle=0,
                pen=pg.mkPen("#d84a4a", width=1, style=Qt.PenStyle.DashLine),
                label=label("integrity.window_threshold")))
        self.closure_plot.setTitle(label("integrity.horizontal_title"))
        self.weight_plot.setTitle(label("integrity.window_scale"))
        self.closure_plot.setLabel("left", "m")
        self.weight_plot.setLabel("left", label("integrity.scale_unit"))
        self.horizontal_note.setText(label("integrity.revision3_explanation"))
        self._Status_Refresh()

    def _Rebuild(self):
        if self._dataset is None or not self._source_available:
            return
        self._result = ReceiverInformation_Build(self._dataset)
        self._horizontal = HorizontalQuality_Build(
            self._dataset, source_kind=self._source_kind,
            window_evidence=self._window_evidence,
            integrity_enabled=self._parameters.get("gnss_integrity_enable"))
        try:
            self._vertical = GnssVerticalConsistency_Build(
                self._dataset,
                max_gap_ms=int(self._parameters.get("gnss_integrity_max_gap_ms", 120)))
        except (ValueError, KeyError, TypeError):
            self._vertical = None
        self._Render()

    @staticmethod
    def _Trace_Draw(plot, time, values, name, color):
        plot.plot(
            time,
            np.asarray(values, dtype=np.float64),
            pen=pg.mkPen(color, width=1.5),
            connect="finite",
            name=name,
        )

    def _Status_Refresh(self):
        trace = self._horizontal
        if trace is None:
            self.status_label.clear()
            return
        summary = HorizontalQualitySummary_Get(trace, self._origin, *self._interval)
        label = self._translator.Text_Get
        source = label("integrity.source." + trace.source_kind)
        if not summary["samples"]:
            self.status_label.setText(source + " · " + label("integrity.current_unavailable"))
            return
        def value(number):
            return "—" if number is None or not np.isfinite(number) else f"{number:.2f}"
        end = label("integrity.end_valid" if summary["end_evidence_valid"]
                    else "integrity.end_unavailable")
        self.status_label.setText(label("integrity.interval_summary",
            source=source, end=end, time=value(summary["end_time_s"]),
            scale=value(summary["end_scale"]),
            valid=summary["valid_samples"], samples=summary["samples"],
            error=value(summary["maximum_closure_m"]),
            peak=value(summary["maximum_scale"]), weighted=summary["weighted_samples"]))

    def _Render(self):
        result = self._result
        vertical = self._vertical
        if result is None:
            return
        _Plot_Reset(self.plots)
        self._speed_view.clear()
        label = self._translator.Text_Get
        time = (result.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        if vertical is not None:
            vertical_time = (vertical.timestamp_us.astype(np.float64) - self._origin) * 1e-6
            self._Trace_Draw(self.vertical_plot, vertical_time, vertical.error_m,
                             label("integrity.vertical_error"), "#2b77c2")
            for timestamp in vertical_time[vertical.chain_reset]:
                self.vertical_plot.addItem(pg.InfiniteLine(
                    pos=float(timestamp), angle=90, pen=pg.mkPen("#9299a5", width=1)))
        for index, key, color in (
            (0, "integrity.hacc", "#2b77c2"),
            (1, "integrity.vacc", "#1a9d6c"),
        ):
            self._Trace_Draw(self.quality_plot, time, result.quality[:, index], label(key), color)
        speed_item = pg.PlotDataItem(
            time,
            result.quality[:, 2],
            pen=pg.mkPen("#ec8a20", width=1.5),
            connect="finite",
        )
        self._speed_view.addItem(speed_item)
        self.quality_plot.getPlotItem().legend.addItem(speed_item, label("integrity.sacc"))
        self._Trace_Draw(
            self.satellite_plot,
            time,
            result.quality[:, 3],
            label("integrity.satellites_label"),
            "#9467bd",
        )
        self.closure_plot.setTitle(label("integrity.horizontal_title"))
        self.vertical_plot.setTitle(label("integrity.vertical_title"))
        self.quality_plot.setTitle(label("integrity.receiver_precision"))
        self.satellite_plot.setTitle(label("integrity.satellites_label"))
        for plot in (self.closure_plot, self.vertical_plot, self.quality_plot):
            plot.setLabel("left", "m")
        self.quality_plot.getAxis("right").setLabel("m/s")
        self.satellite_plot.setLabel("left", label("integrity.satellites_unit"))
        for plot in self.plots:
            plot.setLabel("bottom", label("timeline.time"))
        self.vertical_note.setText(label("integrity.vertical_display_explanation"))
        self.TimeRange_Set(*self._interval)
        self._WindowEvidence_Render()

    def TimeRange_Set(self, start: float, end: float):
        self._interval = (start, end)
        if not np.isfinite(end):
            timestamps = [trace.timestamp_us for trace in (self._result, self._horizontal)
                          if trace is not None and len(trace.timestamp_us)]
            if not timestamps:
                return
            end = (float(max(ts[-1] for ts in timestamps)) - self._origin) * 1e-6
        end = max(end, start + 0.001)
        for plot in self.plots:
            plot.setLimits(xMin=start, xMax=end)
            plot.setXRange(start, end, padding=0)
        self.quality_plot.setXRange(start, end, padding=0)
        self._Status_Refresh()

    def Theme_Apply(self, theme):
        self._theme = theme
        background, foreground = Plot_Colors(theme)
        for plot in self.plots:
            _Plot_Prepare(plot, theme)
        right = self.quality_plot.getAxis("right")
        right.setTextPen(foreground)
        right.setPen(foreground)
        self._speed_view.setBackgroundColor(background)

    def Language_Apply(self, translator):
        self._translator = translator
        selected = self.display_combo.currentData()
        self.display_combo.blockSignals(True)
        self.display_combo.clear()
        for key, value in (
            ("integrity.view.horizontal", "horizontal"),
            ("integrity.view.vertical", "vertical"),
            ("integrity.view.receiver", "receiver"),
        ):
            self.display_combo.addItem(translator.Text_Get(key), value)
        index = self.display_combo.findData(selected)
        self.display_combo.setCurrentIndex(max(index, 0))
        self.display_combo.blockSignals(False)
        self.pages.setCurrentIndex(max(index, 0))
        self.display_label.setText(translator.Text_Get("state.display_content"))
        self._Render()

    def ChartViews_Reset(self):
        _PlotViews_Reset(self.plots)
        self._speed_view.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self._speed_view.updateAutoRange()
