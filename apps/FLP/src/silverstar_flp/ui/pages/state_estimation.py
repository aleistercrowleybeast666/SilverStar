from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import (
    AnalysisSource,
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import (
    EstimatorVisualizationSpec,
    MeasurementGroupSpec,
    StateGroupSpec,
)
from silverstar_flp.plugins.registry import PluginRegistry, builtin_registry
from silverstar_flp.ui.gnss_integrity import GnssIntegrityPage
from silverstar_flp.ui.navigation_diagnostics import NavigationDiagnostics
from silverstar_flp.ui.pages.charts import (
    TraceColorAllocator,
    _NearestIndex,
    _Plot_Prepare,
    _Plot_Reset,
    _PlotViews_Reset,
    _Series_Plot,
    _Source_Label,
)
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox


def _Series_ComponentsSelect(
    series: TimeSeries | None,
    indices: tuple[int, ...],
    columns: tuple[str, ...],
    *,
    unit: str | None = None,
    quantity: str | None = None,
) -> TimeSeries | None:
    if series is None or series.count == 0 or not indices:
        return None
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim == 1:
        values = values.reshape(-1, 1)
    if max(indices) >= values.shape[1]:
        return None
    selected = values[:, indices].copy()
    valid = np.asarray(series.valid, dtype=np.bool_) & np.all(np.isfinite(selected), axis=1)
    return TimeSeries(
        timestamp_us=series.timestamp_us,
        values=selected,
        unit=series.unit if unit is None else unit,
        quantity=series.quantity if quantity is None else quantity,
        source=series.source,
        valid=valid,
        columns=columns,
        metadata={**series.metadata, "display_derived": True},
    )


def _Series_ColumnSelect(series: TimeSeries | None, index: int) -> TimeSeries | None:
    selected = _Series_ComponentsSelect(
        series,
        (index,),
        (),
    )
    if selected is None:
        return None
    return TimeSeries(
        timestamp_us=selected.timestamp_us,
        values=np.asarray(selected.values)[:, 0],
        unit=selected.unit,
        quantity=selected.quantity,
        source=selected.source,
        valid=selected.valid,
        metadata=selected.metadata,
    )


class StateEstimationPage(QWidget):
    """Metadata-driven high-level estimator diagnostics."""

    def __init__(
        self,
        translator: Translator,
        registry: PluginRegistry | None = None,
    ) -> None:
        super().__init__()
        self._translator = translator
        self._registry = registry or builtin_registry()
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        self._resolver: ChannelResolver | None = None
        self._estimator_source: AnalysisSource | None = None
        self._visualization: EstimatorVisualizationSpec | None = None
        self._source_parameters: Mapping[str, object] = {}
        self._interval = (0.0, float("inf"))

        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_value_label = QLabel("—")
        self.source_value_label.setObjectName("muted")
        self.diagnostic_label = QLabel()
        self.diagnostic_label.setObjectName("muted")
        source_row.addWidget(self.source_label)
        source_row.addWidget(self.source_value_label, 1)
        source_row.addWidget(self.diagnostic_label, 2)
        self.reset_charts_button = QPushButton()
        self.reset_charts_button.clicked.connect(self._ChartViews_Reset)
        source_row.addWidget(self.reset_charts_button)
        layout.addLayout(source_row)
        self.navigation_health_label = QLabel()
        self.navigation_health_label.setObjectName("warningLabel")
        self.navigation_health_label.setWordWrap(True)
        layout.addWidget(self.navigation_health_label)

        self.tabs = QTabWidget()
        self._CovarianceTab_Build()
        self._InnovationTab_Build()
        self._NisTab_Build()
        self._MeasurementsTab_Build()
        self.navigation_diagnostics = {}
        for kind in ("landing",):
            panel = NavigationDiagnostics(kind, translator)
            self.navigation_diagnostics[kind] = panel
            self.tabs.addTab(panel, translator.Text_Get("diagnostic." + kind))
        self.gnss_integrity = GnssIntegrityPage(translator)
        self.tabs.insertTab(
            self.tabs.indexOf(self.navigation_diagnostics["landing"]),
            self.gnss_integrity,
            translator.Text_Get("diagnostic.gnss_integrity"),
        )
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def _CovarianceTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.state_group_label = QLabel()
        self.state_group_combo = StandardComboBox()
        self.covariance_display_label = QLabel()
        self.covariance_display_combo = StandardComboBox()
        self.state_group_combo.currentIndexChanged.connect(self._Covariance_Refresh)
        self.covariance_display_combo.currentIndexChanged.connect(self._Covariance_Refresh)
        controls.addWidget(self.state_group_label)
        controls.addWidget(self.state_group_combo)
        controls.addSpacing(12)
        controls.addWidget(self.covariance_display_label)
        controls.addWidget(self.covariance_display_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.covariance_plot = self._Plot_Create()
        layout.addWidget(self.covariance_plot)
        self.state_estimate_plot = self._Plot_Create()
        self.state_estimate_plot.hide()
        layout.addWidget(self.state_estimate_plot)
        self.tabs.addTab(widget, "")

    def _InnovationTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.innovation_measurement_label = QLabel()
        self.innovation_measurement_combo = StandardComboBox()
        self.innovation_measurement_combo.currentIndexChanged.connect(self._Innovation_Refresh)
        controls.addWidget(self.innovation_measurement_label)
        controls.addWidget(self.innovation_measurement_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.innovation_plot = self._Plot_Create()
        layout.addWidget(self.innovation_plot)
        self.tabs.addTab(widget, "")

    def _NisTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        selector = QHBoxLayout()
        self.nis_display_label = QLabel()
        self.nis_display_combo = StandardComboBox()
        self.nis_display_combo.currentIndexChanged.connect(self._NisDisplay_Changed)
        selector.addWidget(self.nis_display_label)
        selector.addWidget(self.nis_display_combo)
        selector.addStretch(1)
        layout.addLayout(selector)
        self.nis_pages = QStackedWidget()
        layout.addWidget(self.nis_pages, 1)

        plot_page = QWidget()
        plot_layout = QVBoxLayout(plot_page)
        controls = QHBoxLayout()
        self.nis_measurement_label = QLabel()
        self.nis_measurement_combo = StandardComboBox()
        self.nis_measurement_combo.currentIndexChanged.connect(self._Nis_Refresh)
        controls.addWidget(self.nis_measurement_label)
        controls.addWidget(self.nis_measurement_combo)
        controls.addStretch(1)
        plot_layout.addLayout(controls)
        self.nis_plot = self._Plot_Create()
        plot_layout.addWidget(self.nis_plot, 1)
        self.nis_pages.addWidget(plot_page)

        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        self.nis_scope_label = QLabel()
        summary_layout.addWidget(self.nis_scope_label)
        self.nis_summary = QTableWidget(4, 6)
        TouchScroll_Enable(self.nis_summary)
        self.nis_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.nis_summary.verticalHeader().setVisible(False)
        self.nis_summary.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        summary_layout.addWidget(self.nis_summary, 1)
        self.nis_pages.addWidget(summary_page)
        self.tabs.addTab(widget, "")

    def _NisDisplay_Changed(self, index: int) -> None:
        if 0 <= index < self.nis_pages.count():
            self.nis_pages.setCurrentIndex(index)

    def TimeRange_Set(self, start: float, end: float) -> None:
        self._interval = (start, end)
        self._NisSummary_Set()

    def _MeasurementsTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.measurement_group_label = QLabel()
        self.measurement_group_combo = StandardComboBox()
        self.measurement_group_combo.currentIndexChanged.connect(self._Measurements_Refresh)
        controls.addWidget(self.measurement_group_label)
        controls.addWidget(self.measurement_group_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.measurement_uncertainty_plot = self._Plot_Create()
        self.measurement_age_plot = self._Plot_Create()
        self._measurement_x_syncing = False
        for plot in (
            self.measurement_uncertainty_plot,
            self.measurement_age_plot,
        ):
            plot.getViewBox().sigXRangeChanged.connect(self._MeasurementXRange_Sync)
        self.measurement_uncertainty_plot.getAxis("bottom").setStyle(showValues=False)
        self.measurement_unavailable_label = QLabel()
        self.measurement_unavailable_label.setObjectName("muted")
        self.measurement_unavailable_label.setWordWrap(True)
        layout.addWidget(self.measurement_unavailable_label)
        splitter.addWidget(self.measurement_uncertainty_plot)
        splitter.addWidget(self.measurement_age_plot)
        layout.addWidget(splitter)
        self.tabs.addTab(widget, "")

    def _Plot_Create(self) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.addLegend()
        _Plot_Prepare(plot, self._theme)
        return plot

    def _Plots_Get(self) -> tuple[pg.PlotWidget, ...]:
        return (
            self.covariance_plot,
            self.state_estimate_plot,
            self.innovation_plot,
            self.nis_plot,
            self.measurement_uncertainty_plot,
            self.measurement_age_plot,
        )

    def _ChartViews_Reset(self) -> None:
        _PlotViews_Reset(self._Plots_Get())
        self.gnss_integrity.ChartViews_Reset()

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver | None = None,
    ) -> None:
        self._dataset = dataset
        self._resolver = resolver or ChannelResolver(dataset, ReplayResultStore())
        self._Estimator_Select()
        for panel in self.navigation_diagnostics.values():
            panel.Dataset_Set(dataset, self._resolver)
        self.gnss_integrity.Dataset_Set(dataset)

    def _Estimator_Select(self) -> None:
        if self._dataset is None or self._resolver is None:
            self._Content_Clear()
            return
        algorithm_ids = tuple(
            plugin.metadata.plugin_id
            for plugin in self._registry.algorithms
            if plugin.metadata.estimator_visualization is not None
        )
        sources = self._resolver.EstimatorSources_Get(algorithm_ids)
        active = self._resolver.store.ActiveSource_Get()
        selected = next(
            (source for source in sources if source.source_id == active.source_id), None
        )
        selected_without_estimator = selected is None and active.kind != AnalysisSourceKind.RECORDED
        if selected_without_estimator:
            selected = next(
                (source for source in sources if source.kind == AnalysisSourceKind.RECORDED),
                None,
            )
        if selected is None:
            self._Content_Clear()
            self._FirmwareEstimatorDiagnostic_Append()
            return
        try:
            plugin = self._registry.Algorithm_Get(str(selected.algorithm_id))
        except KeyError:
            self._Content_Clear()
            return
        visualization = plugin.metadata.estimator_visualization
        if visualization is None:
            self._Content_Clear()
            return
        self._estimator_source = selected
        self._visualization = visualization
        if selected.kind == AnalysisSourceKind.RECORDED:
            self._source_parameters = plugin.recorded_parameters(self._dataset)
            self.diagnostic_label.setText(self._translator.Text_Get("state.recorded_diagnostic"))
        else:
            entry = self._resolver.store.SourceEntry_Get(selected.source_id)
            self._source_parameters = entry.parameters if entry is not None else {}
            self.diagnostic_label.setText(self._translator.Text_Get("state.recomputed_diagnostic"))
        if selected_without_estimator:
            self.diagnostic_label.setText(self._translator.Text_Get("state.selected_no_estimator"))
        self._FirmwareEstimatorDiagnostic_Append()
        self.source_value_label.setText(
            _Source_Label(self._translator, self._resolver, selected.source_id)
        )
        self.gnss_integrity.Parameters_Set(self._source_parameters)
        entry = self._resolver.store.SourceEntry_Get(selected.source_id)
        from silverstar_flp.decoder_profiles.eskf15_records import NavigationWindows_Get

        windows = entry.diagnostics.get("window_evidence") if entry is not None else None
        if entry is None and self._dataset.Records_Get("NAV_QUALITY"):
            windows = NavigationWindows_Get(self._dataset.Records_Get("NAV_QUALITY"))
        self.gnss_integrity.WindowEvidence_Set(windows)
        self._Selectors_Refresh()
        self._Refresh()

    def _FirmwareEstimatorDiagnostic_Append(self) -> None:
        if self._dataset is None or self._dataset.semantic_context is None:
            return
        plugin_components = {
            component_id
            for plugin in self._registry.algorithms
            if plugin.metadata.estimator_visualization is not None
            for component_id in plugin.metadata.firmware_component_ids
        }
        unmatched = tuple(
            component_id
            for component_id in self._dataset.semantic_context.FirmwareAlgorithms_Get()
            if ".estimator." in component_id and component_id not in plugin_components
        )
        if not unmatched:
            return
        diagnostic = self._translator.Text_Get(
            "state.firmware_estimator_without_plugin",
            values=", ".join(unmatched),
        )
        current = self.diagnostic_label.text().strip()
        self.diagnostic_label.setText(f"{current} · {diagnostic}" if current else diagnostic)

    def _SourceScore_Get(self, source: AnalysisSource) -> int:
        if self._resolver is None or source.algorithm_id is None:
            return -1
        try:
            plugin = self._registry.Algorithm_Get(source.algorithm_id)
        except KeyError:
            return -1
        visualization = plugin.metadata.estimator_visualization
        if visualization is None:
            return -1
        channels = [group.covariance_channel for group in visualization.state_groups]
        for group in visualization.measurement_groups:
            channels.extend(
                (
                    group.innovation_channel,
                    group.nis_channel,
                    group.update_result_channel,
                    group.r_scale_channel,
                    group.measurement_age_channel,
                    group.fixed_lag_latency_channel,
                    group.measurement_uncertainty_channel,
                    group.effective_r_channel,
                )
            )
        return sum(
            bool(channel_id) and self._resolver.Series_Get(channel_id, source.source_id) is not None
            for channel_id in channels
        )

    def _Content_Clear(self) -> None:
        self._estimator_source = None
        self._visualization = None
        self._source_parameters = {}
        self.source_value_label.setText(self._translator.Text_Get("status.na"))
        self.diagnostic_label.setText(self._translator.Text_Get("state.no_estimator_metadata"))
        for combo in (
            self.state_group_combo,
            self.innovation_measurement_combo,
            self.nis_measurement_combo,
            self.measurement_group_combo,
        ):
            combo.clear()
        _Plot_Reset(self._Plots_Get())
        self.nis_summary.clearContents()

    def _Selectors_Refresh(self) -> None:
        if self._visualization is None:
            return
        self._Combo_Refresh(
            self.state_group_combo,
            (
                (group.group_id, self._translator.Text_Get(group.label_key))
                for group in self._visualization.state_groups
            ),
        )
        measurement_items = tuple(
            (
                group.measurement_group_id,
                self._translator.Text_Get(group.label_key),
            )
            for group in self._visualization.measurement_groups
        )
        for combo in (
            self.innovation_measurement_combo,
            self.nis_measurement_combo,
            self.measurement_group_combo,
        ):
            self._Combo_Refresh(combo, measurement_items)
        display = str(self.covariance_display_combo.currentData() or "standard_deviation")
        self.covariance_display_combo.blockSignals(True)
        self.covariance_display_combo.clear()
        self.covariance_display_combo.addItem(
            self._translator.Text_Get("state.standard_deviation_1sigma"),
            "standard_deviation",
        )
        self.covariance_display_combo.addItem(
            self._translator.Text_Get("state.variance_pii"),
            "variance",
        )
        index = self.covariance_display_combo.findData(display)
        self.covariance_display_combo.setCurrentIndex(max(index, 0))
        self.covariance_display_combo.blockSignals(False)

    @staticmethod
    def _Combo_Refresh(
        combo: StandardComboBox,
        items: object,
    ) -> None:
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for item_id, label in items:
            combo.addItem(label, item_id)
        index = combo.findData(selected)
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def _Refresh(self) -> None:
        if self._visualization is None:
            return
        health = self._Series_Get(self._visualization.navigation_health_channel)
        self.navigation_health_label.setVisible(health is not None)
        if health is not None and health.count:
            names = ("warmup", "healthy", "degraded", "dead_reckoning", "invalid")
            value = int(health.values[-1])
            state = names[value] if 0 <= value < len(names) else "invalid"
            self.navigation_health_label.setText(
                self._translator.Text_Get(
                    "state.navigation_health",
                    value=self._translator.Text_Get("navigation." + state),
                )
            )
        self._Covariance_Refresh()
        self._Innovation_Refresh()
        self._Nis_Refresh()
        self._Measurements_Refresh()
        self._NisSummary_Set()

    def _StartTimestamp_Get(self) -> int:
        if self._dataset is None:
            return 0
        return self._dataset.start_timestamp_us or self._dataset.diagnostics.first_timestamp_us or 0

    def _Series_Get(self, channel_id: str) -> TimeSeries | None:
        if not channel_id or self._resolver is None or self._estimator_source is None:
            return None
        return self._resolver.Series_Get(channel_id, self._estimator_source.source_id)

    def _ReferenceSeries_Get(self, channel_id: str) -> TimeSeries | None:
        if (
            not channel_id
            or self._resolver is None
            or self._estimator_source is None
            or self._estimator_source.kind == AnalysisSourceKind.RECORDED
        ):
            return None
        selected = self._Series_Get(channel_id)
        recorded = self._resolver.RecordedSeries_Get(channel_id)
        return recorded if selected is not None else None

    def _ReferenceLabel_Get(self) -> str:
        if self._resolver is None:
            return self._translator.Text_Get("status.recorded")
        return _Source_Label(self._translator, self._resolver, ReplayResultStore.RECORDED_SOURCE_ID)

    def _StateGroup_Get(self) -> StateGroupSpec | None:
        if self._visualization is None:
            return None
        group_id = self.state_group_combo.currentData()
        return next(
            (group for group in self._visualization.state_groups if group.group_id == group_id),
            None,
        )

    def _MeasurementGroup_Get(
        self,
        combo: StandardComboBox,
    ) -> MeasurementGroupSpec | None:
        if self._visualization is None:
            return None
        group_id = combo.currentData()
        return next(
            (
                group
                for group in self._visualization.measurement_groups
                if group.measurement_group_id == group_id
            ),
            None,
        )

    def _Covariance_Refresh(self) -> None:
        _Plot_Reset((self.covariance_plot, self.state_estimate_plot))
        group = self._StateGroup_Get()
        self.state_estimate_plot.setVisible(bool(group and group.estimate_channel))
        if group is None:
            return
        group_label = self._translator.Text_Get(group.label_key)
        display = self.covariance_display_combo.currentData()
        unit = f"({group.unit})²" if display == "variance" else group.unit
        if display == "variance" and group.unit in ("", "1"):
            unit = "1"
        colors = TraceColorAllocator()
        for raw_source, reference in (
            (self._ReferenceSeries_Get(group.covariance_channel), True),
            (self._Series_Get(group.covariance_channel), False),
        ):
            raw = _Series_ComponentsSelect(
                raw_source,
                group.covariance_diagonal_indices,
                group.component_names,
            )
            if raw is None:
                continue
            values = np.asarray(raw.values, dtype=np.float64).copy()
            if display == "variance":
                columns = tuple(f"P({name},{name})" for name in group.component_names)
            else:
                values[values < 0.0] = np.nan
                values = np.sqrt(values)
                columns = tuple(
                    self._translator.Text_Get(
                        "state.standard_deviation_trace",
                        group=group_label,
                        component=name,
                    )
                    for name in group.component_names
                )
            series = TimeSeries(
                timestamp_us=raw.timestamp_us,
                values=values,
                unit=unit,
                quantity="covariance",
                source=raw.source,
                valid=raw.valid & np.all(np.isfinite(values), axis=1),
                columns=columns,
                metadata=raw.metadata,
            )
            _Series_Plot(
                self.covariance_plot,
                series,
                self._StartTimestamp_Get(),
                colors=colors,
                prefix=f"{self._ReferenceLabel_Get()} · " if reference else "",
                reference=reference,
            )
        self.covariance_plot.setTitle(
            f"{self._translator.Text_Get('chart.covariance')} · {group_label}"
        )
        self.covariance_plot.setLabel("left", unit)
        if group.estimate_channel:
            for series, reference in (
                (self._ReferenceSeries_Get(group.estimate_channel), True),
                (self._Series_Get(group.estimate_channel), False),
            ):
                _Series_Plot(
                    self.state_estimate_plot,
                    series,
                    self._StartTimestamp_Get(),
                    colors=colors,
                    prefix=f"{self._ReferenceLabel_Get()} · " if reference else "",
                    reference=reference,
                )
            self.state_estimate_plot.setTitle(
                self._translator.Text_Get("state.estimate_title", group=group_label)
            )
            self.state_estimate_plot.setLabel("left", group.unit)

    def _MeasurementSeries_Get(
        self,
        channel_id: str,
        group: MeasurementGroupSpec,
        *,
        reference: bool = False,
    ) -> TimeSeries | None:
        return _Series_ComponentsSelect(
            (self._ReferenceSeries_Get(channel_id) if reference else self._Series_Get(channel_id)),
            tuple(range(group.dimension)),
            group.component_names,
        )

    def _Innovation_Refresh(self) -> None:
        _Plot_Reset((self.innovation_plot,))
        group = self._MeasurementGroup_Get(self.innovation_measurement_combo)
        if group is None:
            return
        series = self._MeasurementSeries_Get(group.innovation_channel, group)
        reference = self._MeasurementSeries_Get(group.innovation_channel, group, reference=True)
        label = self._translator.Text_Get(group.label_key)
        _Series_Plot(
            self.innovation_plot,
            reference,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
            prefix=f"{self._ReferenceLabel_Get()} · ",
            reference=True,
        )
        _Series_Plot(
            self.innovation_plot,
            series,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
            prefix=f"{self._translator.Text_Get('chart.innovation')} ",
        )
        self.innovation_plot.setTitle(f"{self._translator.Text_Get('chart.innovation')} · {label}")
        if series is not None:
            self.innovation_plot.setLabel("left", series.unit)

    def _Nis_Refresh(self) -> None:
        _Plot_Reset((self.nis_plot,))
        group = self._MeasurementGroup_Get(self.nis_measurement_combo)
        if group is None:
            return
        series = self._Series_Get(group.nis_channel)
        colors = TraceColorAllocator()
        _Series_Plot(
            self.nis_plot,
            self._ReferenceSeries_Get(group.nis_channel),
            self._StartTimestamp_Get(),
            colors=colors,
            prefix=f"{self._ReferenceLabel_Get()} · NIS",
            reference=True,
        )
        _Series_Plot(
            self.nis_plot,
            series,
            self._StartTimestamp_Get(),
            colors=colors,
            prefix="NIS",
            width=1.8,
        )
        for threshold in group.NisThresholds_Get():
            self._NisThreshold_Plot(
                series,
                threshold.parameter_id,
                threshold.label_key,
                Qt.PenStyle.DashDotLine if threshold.hard else Qt.PenStyle.DashLine,
                colors,
            )
        label = self._translator.Text_Get(group.label_key)
        title = f"{self._translator.Text_Get('chart.nis_full')} · {label}"
        if group.nis_description_key:
            title += "<br>" + self._translator.Text_Get(group.nis_description_key)
        self.nis_plot.setTitle(title)
        self.nis_plot.setLabel("left", "1")

    def _NisThreshold_Plot(
        self,
        series: TimeSeries | None,
        parameter_id: str,
        label_key: str,
        style: Qt.PenStyle,
        colors: TraceColorAllocator,
    ) -> None:
        if series is None or not parameter_id:
            return
        try:
            threshold = float(self._source_parameters[parameter_id])
        except (KeyError, TypeError, ValueError):
            return
        if not np.isfinite(threshold):
            return
        selected = np.flatnonzero(
            series.valid & (series.timestamp_us >= np.uint64(self._StartTimestamp_Get()))
        )
        if selected.size == 0:
            return
        time = (
            series.timestamp_us[selected[[0, -1]]].astype(np.float64)
            - float(self._StartTimestamp_Get())
        ) * 1.0e-6
        self.nis_plot.plot(
            time,
            np.asarray((threshold, threshold), dtype=np.float64),
            pen=pg.mkPen(colors.Color_Next(), width=1.4, style=style),
            name=self._translator.Text_Get(label_key),
        )

    def _MeasurementSigma_Get(
        self,
        channel_id: str,
        group: MeasurementGroupSpec,
        *,
        reference: bool = False,
    ) -> TimeSeries | None:
        variance = self._MeasurementSeries_Get(channel_id, group, reference=reference)
        if variance is None:
            return None
        values = np.asarray(variance.values, dtype=np.float64).copy()
        values[values <= 0] = np.nan
        sigma = np.sqrt(values)
        return TimeSeries(
            timestamp_us=variance.timestamp_us,
            values=sigma,
            unit=group.unit,
            quantity="measurement_sigma",
            source=variance.source,
            valid=variance.valid & np.all(np.isfinite(sigma), axis=1),
            columns=group.component_names,
            metadata={**variance.metadata, "display_derived": True},
        )

    def _MeasurementXRange_Sync(self, source: pg.ViewBox, x_range: tuple[float, float]) -> None:
        if self._measurement_x_syncing:
            return
        self._measurement_x_syncing = True
        try:
            for plot in (
                self.measurement_uncertainty_plot,
                self.measurement_age_plot,
            ):
                view = plot.getViewBox()
                if view is not source:
                    view.setXRange(*x_range, padding=0)
        finally:
            self._measurement_x_syncing = False

    def _MeasurementAxes_Align(self) -> None:
        plots = (
            self.measurement_uncertainty_plot,
            self.measurement_age_plot,
        )
        metrics = QFontMetrics(self.font())
        width = max(88, metrics.horizontalAdvance("−00000.0000") + 24)
        for plot in plots:
            plot.getAxis("left").setWidth(width)

    def _Measurements_Refresh(self) -> None:
        plots = (
            self.measurement_uncertainty_plot,
            self.measurement_age_plot,
        )
        _Plot_Reset(plots)
        group = self._MeasurementGroup_Get(self.measurement_group_combo)
        if group is None:
            self.measurement_unavailable_label.clear()
            return
        label = self._translator.Text_Get(group.label_key)
        sigma_colors = TraceColorAllocator()
        input_sigma = self._MeasurementSigma_Get(group.measurement_uncertainty_channel, group)
        effective_sigma = self._MeasurementSigma_Get(group.effective_r_channel, group)
        for series, label_key, channel_id in (
            (input_sigma, "state.input_sigma", group.measurement_uncertainty_channel),
            (effective_sigma, "state.effective_sigma", group.effective_r_channel),
        ):
            reference = self._MeasurementSigma_Get(channel_id, group, reference=True)
            _Series_Plot(
                self.measurement_uncertainty_plot,
                reference,
                self._StartTimestamp_Get(),
                colors=sigma_colors,
                prefix=f"{self._ReferenceLabel_Get()} · {self._translator.Text_Get(label_key)} · ",
                reference=True,
            )
            _Series_Plot(
                self.measurement_uncertainty_plot,
                series,
                self._StartTimestamp_Get(),
                colors=sigma_colors,
                prefix=f"{self._translator.Text_Get(label_key)} · ",
            )
        unavailable = []
        if input_sigma is None or not np.any(input_sigma.valid):
            unavailable.append(self._translator.Text_Get("state.input_sigma"))
        if effective_sigma is None or not np.any(effective_sigma.valid):
            unavailable.append(self._translator.Text_Get("state.effective_sigma"))
        self.measurement_unavailable_label.setText(
            self._translator.Text_Get(
                "state.measurement_unavailable", values=", ".join(unavailable)
            )
            if unavailable
            else ""
        )
        timing_colors = TraceColorAllocator()
        receive_age = self._Series_Get(group.measurement_age_channel)
        fixed_lag = self._Series_Get(group.fixed_lag_latency_channel)
        for series, label_key, channel_id in (
            (receive_age, "state.receive_age", group.measurement_age_channel),
            (fixed_lag, "state.fixed_lag_latency", group.fixed_lag_latency_channel),
        ):
            _Series_Plot(
                self.measurement_age_plot,
                self._ReferenceSeries_Get(channel_id),
                self._StartTimestamp_Get(),
                colors=timing_colors,
                prefix=f"{self._ReferenceLabel_Get()} · {self._translator.Text_Get(label_key)}",
                reference=True,
            )
            _Series_Plot(
                self.measurement_age_plot,
                series,
                self._StartTimestamp_Get(),
                colors=timing_colors,
                prefix=self._translator.Text_Get(label_key),
            )
        self.measurement_uncertainty_plot.setTitle(
            f"{self._translator.Text_Get('state.measurement_sigma')} · {label}"
        )
        self.measurement_age_plot.setTitle(
            f"{self._translator.Text_Get('state.measurement_timing')} · {label}"
        )
        self.measurement_uncertainty_plot.setLabel("left", group.unit)
        self.measurement_age_plot.setLabel("left", "ms")
        self._MeasurementAxes_Align()

    def _NisSummary_Set(self) -> None:
        groups = (
            ()
            if self._visualization is None
            else tuple(
                group
                for group in self._visualization.measurement_groups
                if group.measurement_group_id.startswith("gnss_")
            )
        )
        self.nis_summary.clearContents()
        for row, group in enumerate(groups[:4]):
            results = self._Series_Get(group.update_result_channel)
            nis = self._Series_Get(group.nis_channel)
            values = np.asarray([], dtype=np.float64)
            if results is not None:
                raw = np.asarray(results.values, dtype=np.float64)
                if raw.ndim > 1:
                    column = group.update_result_index
                    raw = raw[:, column] if column < raw.shape[1] else raw[:, 0]
                times = (
                    results.timestamp_us.astype(np.float64) - self._StartTimestamp_Get()
                ) * 1e-6
                visible = (
                    results.valid & (times >= self._interval[0]) & (times <= self._interval[1])
                )
                values = raw[visible]
            counts = (int(np.count_nonzero(values == code)) for code in (0, 1, 2))
            p95 = np.nan
            if nis is not None:
                raw = np.asarray(nis.values, dtype=np.float64)
                if raw.ndim > 1:
                    raw = raw[:, 0]
                times = (nis.timestamp_us.astype(np.float64) - self._StartTimestamp_Get()) * 1e-6
                visible = (
                    nis.valid
                    & np.isfinite(raw)
                    & (times >= self._interval[0])
                    & (times <= self._interval[1])
                )
                valid = raw[visible]
                if valid.size:
                    p95 = float(np.percentile(valid, 95))
            latest = self._UpdateResult_Text(values[-1]) if values.size else "—"
            cells = (
                self._translator.Text_Get(group.label_key),
                *(str(value) for value in counts),
                self._Number_Text(p95),
                latest,
            )
            for column, value in enumerate(cells):
                self.nis_summary.setItem(row, column, QTableWidgetItem(value))

    @staticmethod
    def _SeriesValue_Get(series: TimeSeries, row: int, column: int) -> float:
        raw = np.asarray(series.values[row], dtype=np.float64)
        if raw.ndim == 0:
            return float(raw) if column == 0 else np.nan
        return float(raw[column]) if column < raw.size else np.nan

    @classmethod
    def _NearestValue_Get(
        cls,
        series: TimeSeries | None,
        timestamp_us: int,
        column: int,
        *,
        fallback: float = np.nan,
    ) -> float:
        if series is None or series.count == 0:
            return fallback
        index = _NearestIndex(series.timestamp_us, timestamp_us)
        return cls._SeriesValue_Get(series, index, column)

    @staticmethod
    def _Number_Text(value: float) -> str:
        return "—" if not np.isfinite(value) else f"{value:.6g}"

    def _UpdateResult_Text(self, value: float) -> str:
        codes = {
            0: "update.accepted",
            1: "update.soft_weighted",
            2: "update.nis_rejected",
            3: "update.invalid",
            4: "update.numeric_error",
            5: "update.not_attempted",
            -1: "update.not_attempted",
        }
        code = (
            codes.get(int(value), "update.unknown")
            if np.isfinite(value)
            else "update.not_attempted"
        )
        return self._translator.Text_Get(code)

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in self._Plots_Get():
            _Plot_Prepare(plot, theme)
        self.gnss_integrity.Theme_Apply(theme)
        self._MeasurementAxes_Align()

    def Language_Apply(self, translator: Translator) -> None:
        self.gnss_integrity.Language_Apply(translator)
        self.tabs.setTabText(
            self.tabs.indexOf(self.gnss_integrity), translator.Text_Get("diagnostic.gnss_integrity")
        )
        for kind, panel in self.navigation_diagnostics.items():
            panel.translator = translator
            panel.model.translator = translator
            if hasattr(panel, "_dataset"):
                panel.Dataset_Set(panel._dataset, panel._resolver)
            self.tabs.setTabText(
                self.tabs.indexOf(panel), translator.Text_Get("diagnostic." + kind)
            )
        self._translator = translator
        self.source_label.setText(translator.Text_Get("label.estimator_source"))
        self.reset_charts_button.setText(translator.Text_Get("action.reset_charts"))
        self.reset_charts_button.setToolTip(translator.Text_Get("action.reset_charts_tooltip"))
        selected_nis = self.nis_display_combo.currentData()
        self.nis_display_combo.blockSignals(True)
        self.nis_display_combo.clear()
        for key, value in (("state.nis_curve", "curve"), ("state.nis_groups", "groups")):
            self.nis_display_combo.addItem(translator.Text_Get(key), value)
        nis_index = self.nis_display_combo.findData(selected_nis)
        self.nis_display_combo.setCurrentIndex(max(nis_index, 0))
        self.nis_display_combo.blockSignals(False)
        self.nis_pages.setCurrentIndex(max(nis_index, 0))
        self.nis_display_label.setText(translator.Text_Get("state.display_content"))
        self.nis_scope_label.setText(translator.Text_Get("state.nis_scope_current_range"))
        self.state_group_label.setText(translator.Text_Get("state.state_group"))
        self.covariance_display_label.setText(translator.Text_Get("state.display"))
        for label in (
            self.innovation_measurement_label,
            self.nis_measurement_label,
            self.measurement_group_label,
        ):
            label.setText(translator.Text_Get("state.measurement"))
        tab_codes = (
            "tab.covariance",
            "tab.innovation",
            "tab.nis_full",
            "tab.measurements",
        )
        for index, code in enumerate(tab_codes):
            self.tabs.setTabText(index, translator.Text_Get(code))
        for plot in self._Plots_Get():
            plot.setLabel("bottom", translator.Text_Get("timeline.time"))
        self.nis_summary.setHorizontalHeaderLabels(
            [
                translator.Text_Get("state.measurement"),
                translator.Text_Get("state.accepted_count"),
                translator.Text_Get("state.soft_count"),
                translator.Text_Get("state.rejected_count"),
                "NIS P95",
                translator.Text_Get("state.latest"),
            ]
        )
        if self._visualization is not None:
            self._Selectors_Refresh()
            self._Refresh()
            if self._resolver is not None and self._estimator_source is not None:
                self.source_value_label.setText(
                    _Source_Label(
                        self._translator,
                        self._resolver,
                        self._estimator_source.source_id,
                    )
                )
                active = self._resolver.store.ActiveSource_Get()
                code = (
                    "state.selected_no_estimator"
                    if active.kind != AnalysisSourceKind.RECORDED
                    and self._estimator_source.kind == AnalysisSourceKind.RECORDED
                    else "state.recorded_diagnostic"
                    if self._estimator_source.kind == AnalysisSourceKind.RECORDED
                    else "state.recomputed_diagnostic"
                )
                self.diagnostic_label.setText(self._translator.Text_Get(code))
                self._FirmwareEstimatorDiagnostic_Append()
