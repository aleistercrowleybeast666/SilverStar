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

from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build
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
        self._result = None
        self._vertical = None
        self._window_evidence = None
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
        horizontal_layout.addWidget(self.horizontal_note)
        horizontal_layout.addWidget(self.status_label)
        self.closure_plot = pg.PlotWidget()
        horizontal_layout.addWidget(self.closure_plot, 1)
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
        self.plots = (self.closure_plot, self.vertical_plot, self.quality_plot, self.satellite_plot)
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
        self._origin = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        self._Rebuild()

    def Parameters_Set(self, parameters):
        self._parameters = dict(parameters or {})
        # Display evidence from old logs even when their firmware lacked the policy.
        self._parameters["gnss_integrity_enable"] = 1
        self._Rebuild()

    def WindowEvidence_Set(self, evidence):
        self._window_evidence = evidence
        self._WindowEvidence_Render()

    def _WindowEvidence_Render(self):
        if self._window_evidence is None:
            return
        self.closure_plot.clear()
        if self.closure_plot.getPlotItem().legend is not None:
            self.closure_plot.getPlotItem().legend.clear()
        usable = [item for item in self._window_evidence if item["valid"]]
        if usable:
            times = [
                ((item.get("evaluation_us") or item["end_us"]) - self._origin) * 1e-6
                for item in usable
            ]
            closure = [float(np.linalg.norm(item["closure_en"])) for item in usable]
            self._Trace_Draw(
                self.closure_plot,
                times,
                closure,
                self._translator.Text_Get("integrity.window_error"),
                "#2b77c2",
            )
        self.horizontal_note.setText(self._translator.Text_Get("integrity.window_explanation"))
        self._Status_Refresh()

    def _Rebuild(self):
        if self._dataset is None:
            return
        try:
            self._result = GnssIntegrityStream_Build(self._dataset, self._parameters)
            self._vertical = GnssVerticalConsistency_Build(
                self._dataset,
                max_gap_ms=int(self._parameters.get("gnss_integrity_max_gap_ms", 120)),
            )
        except (ValueError, KeyError, TypeError) as error:
            self._result = None
            self._vertical = None
            self.horizontal_note.setText(str(error))
            _Plot_Reset(self.plots)
            self._speed_view.clear()
            return
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

    def _RecordedTransitions_Get(self):
        if self._dataset is None:
            return ()
        transitions = []
        for record in self._dataset.Records_Get("EVENT"):
            if int(record.payload.get("event_id", -1)) != 0x2E:
                continue
            packed = int(record.payload.get("arg0", 0))
            previous = packed & 0xFF
            current = (packed >> 8) & 0xFF
            if previous in (0, 1, 2) and current in (0, 1, 2):
                transitions.append((int(record.timestamp_us), current))
        return tuple(sorted(transitions))

    def _Markers_Draw(self, plot, time, result):
        for index in np.flatnonzero(result.chain_reset):
            plot.addItem(
                pg.InfiniteLine(
                    pos=float(time[index]),
                    angle=90,
                    pen=pg.mkPen("#9299a5", width=1),
                )
            )
        recorded = self._RecordedTransitions_Get()
        if recorded:
            transitions = (
                (float(timestamp - self._origin) * 1e-6, state) for timestamp, state in recorded
            )
        else:
            transitions = (
                (float(time[index]), int(result.state[index]))
                for index in range(1, len(result.state))
                if result.state[index] != result.state[index - 1]
            )
        for stamp, state in transitions:
            color = ("#1a9d6c", "#ec8a20", "#d84a4a")[state]
            plot.addItem(
                pg.InfiniteLine(
                    pos=stamp,
                    angle=90,
                    pen=pg.mkPen(color, width=2),
                )
            )

    def _Status_Refresh(self):
        if self._window_evidence is not None:
            end_us = (
                self._origin + int(self._interval[1] * 1e6)
                if np.isfinite(self._interval[1])
                else None
            )
            eligible = [
                item
                for item in self._window_evidence
                if item["valid"]
                and (
                    end_us is None
                    or (item.get("evaluation_us") or item["end_us"])
                    <= end_us
                    <= (item.get("evaluation_us") or item["end_us"]) + 6_000_000
                )
            ]
            self.status_label.setText(
                self._translator.Text_Get(
                    "integrity.window_weight" if eligible else "integrity.window_warmup",
                    value=f"{eligible[-1]['variance_scale']:.3g}" if eligible else "1",
                )
            )
            return
        if self._result is None or not self._result.timestamp_us.size:
            self.status_label.setText("")
            return
        end = self._interval[1]
        end_timestamp = self._origin + round(end * 1e6) if np.isfinite(end) else None
        recorded = self._RecordedTransitions_Get()
        if recorded:
            current = 0
            for timestamp, state in recorded:
                if end_timestamp is not None and timestamp > end_timestamp:
                    break
                current = state
            prefix = "integrity.recorded_state"
        else:
            index = (
                int(np.searchsorted(self._result.timestamp_us, end_timestamp, side="right")) - 1
                if end_timestamp is not None
                else len(self._result.timestamp_us) - 1
            )
            current = int(self._result.state[max(index, 0)])
            prefix = "integrity.offline_state"
        state_key = ("normal", "suspect", "rejected")[current]
        self.status_label.setText(
            self._translator.Text_Get(prefix).format(
                state=self._translator.Text_Get("integrity.state." + state_key),
            )
        )

    def _Render(self):
        result = self._result
        vertical = self._vertical
        if result is None or vertical is None:
            return
        _Plot_Reset(self.plots)
        self._speed_view.clear()
        label = self._translator.Text_Get
        time = (result.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        horizontal = result.closure_norm_m.copy()
        horizontal[result.chain_reset] = np.nan
        self._Trace_Draw(
            self.closure_plot, time, horizontal, label("integrity.horizontal_error"), "#2b77c2"
        )
        for threshold, key, color in (
            (
                self._parameters.get("gnss_integrity_error_threshold_m", 10.0),
                "integrity.error_threshold",
                "#d84a4a",
            ),
            (
                self._parameters.get("gnss_integrity_recovery_threshold_m", 4.0),
                "integrity.recovery_threshold",
                "#1a9d6c",
            ),
        ):
            self.closure_plot.addItem(
                pg.InfiniteLine(
                    pos=float(threshold),
                    angle=0,
                    pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine),
                    label=label(key),
                )
            )
        self._Markers_Draw(self.closure_plot, time, result)
        vertical_time = (vertical.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        self._Trace_Draw(
            self.vertical_plot,
            vertical_time,
            vertical.error_m,
            label("integrity.vertical_error"),
            "#2b77c2",
        )
        self.vertical_plot.addItem(
            pg.InfiniteLine(
                pos=0,
                angle=0,
                pen=pg.mkPen("#9299a5", width=1, style=Qt.PenStyle.DashLine),
                label=label("integrity.zero_reference"),
            )
        )
        for index in np.flatnonzero(vertical.chain_reset):
            self.vertical_plot.addItem(
                pg.InfiniteLine(
                    pos=float(vertical_time[index]),
                    angle=90,
                    pen=pg.mkPen("#9299a5", width=1),
                )
            )
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
        self.horizontal_note.setText(label("integrity.horizontal_explanation"))
        self.vertical_note.setText(label("integrity.vertical_offline_only"))
        self.TimeRange_Set(*self._interval)
        self._WindowEvidence_Render()

    def TimeRange_Set(self, start: float, end: float):
        self._interval = (start, end)
        if not np.isfinite(end):
            if self._result is None or not len(self._result.timestamp_us):
                return
            end = (float(self._result.timestamp_us[-1]) - self._origin) * 1e-6
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
