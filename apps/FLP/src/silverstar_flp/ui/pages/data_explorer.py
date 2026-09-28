from __future__ import annotations

import json
from collections.abc import Mapping

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.comparison import Series_SamplingGet
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.time_range import DisplayIndices_Get
from silverstar_flp.plugins.api.algorithm import AlgorithmResult
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox


class DataExplorerPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._dataset: FlightDataset | None = None
        self._time_range = None
        self._channels: dict[str, TimeSeries] = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        channel_widget = QWidget()
        channel_layout = QVBoxLayout(channel_widget)
        channel_filter_layout = QHBoxLayout()
        self.channel_group_combo = StandardComboBox()
        self.channel_group_combo.currentIndexChanged.connect(self._Channels_Filter)
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._Channels_Filter)
        channel_filter_layout.addWidget(self.channel_group_combo)
        channel_filter_layout.addWidget(self.search_edit, 1)
        channel_layout.addLayout(channel_filter_layout)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.channel_list = QListWidget()
        TouchScroll_Enable(self.channel_list)
        self.channel_list.currentItemChanged.connect(self._Channel_Show)
        splitter.addWidget(self.channel_list)
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        self.channel_metadata = QLabel("—")
        self.channel_metadata.setWordWrap(True)
        self.channel_metadata.setObjectName("muted")
        detail_layout.addWidget(self.channel_metadata)
        self.channel_table = QTableWidget()
        TouchScroll_Enable(self.channel_table)
        self.channel_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.channel_table.verticalHeader().setVisible(False)
        detail_layout.addWidget(self.channel_table, 1)
        self.display_note = QLabel(
            "The table is display-downsampled above 5,000 rows; exports retain every sample."
        )
        self.display_note.setObjectName("muted")
        detail_layout.addWidget(self.display_note)
        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        channel_layout.addWidget(splitter)
        self.tabs.addTab(channel_widget, "")

        record_widget = QWidget()
        record_layout = QVBoxLayout(record_widget)
        selector_layout = QHBoxLayout()
        self.record_type_label = QLabel()
        selector_layout.addWidget(self.record_type_label)
        self.record_combo = StandardComboBox()
        self.record_combo.currentIndexChanged.connect(self._Records_Show)
        selector_layout.addWidget(self.record_combo, 1)
        record_layout.addLayout(selector_layout)
        self.record_metadata = QLabel("—")
        self.record_metadata.setObjectName("muted")
        self.record_metadata.setWordWrap(True)
        self.record_metadata.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        record_layout.addWidget(self.record_metadata)
        self.record_table = QTableWidget()
        TouchScroll_Enable(self.record_table)
        self.record_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.record_table.verticalHeader().setVisible(False)
        record_layout.addWidget(self.record_table)
        self.tabs.addTab(record_widget, "")

        diagnostics_widget = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_widget)
        self.diagnostics_summary = QLabel("—")
        self.diagnostics_summary.setObjectName("muted")
        self.diagnostics_summary.setWordWrap(True)
        self.diagnostics_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        diagnostics_layout.addWidget(self.diagnostics_summary)
        self.diagnostics_table = QTableWidget()
        TouchScroll_Enable(self.diagnostics_table)
        self.diagnostics_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.diagnostics_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.diagnostics_table.verticalHeader().setVisible(False)
        diagnostics_layout.addWidget(self.diagnostics_table)
        self.sequence_gap_table = QTableWidget()
        TouchScroll_Enable(self.sequence_gap_table)
        self.sequence_gap_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sequence_gap_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sequence_gap_table.verticalHeader().setVisible(False)
        diagnostics_layout.addWidget(self.sequence_gap_table)
        self.tabs.addTab(diagnostics_widget, "")
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        results: ReplayResultStore | Mapping[str, AlgorithmResult] | None = None,
    ) -> None:
        self._dataset = dataset
        if isinstance(results, ReplayResultStore):
            self._channels = ChannelResolver(dataset, results).ExplorerChannels_Get()
        else:
            self._channels = dict(dataset.series)
            for result_name, result in (results or {}).items():
                for channel_id, series in result.channels.items():
                    self._channels[f"{result_name}.{channel_id}"] = series
        checked_before = {
            self.channel_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.channel_list.count())
            if self.channel_list.item(index).checkState() == Qt.CheckState.Checked
        }
        self.channel_list.clear()
        for channel_id in sorted(self._channels):
            series = self._channels[channel_id]
            item = QListWidgetItem(f"{channel_id}  ({series.count})")
            item.setData(Qt.ItemDataRole.UserRole, channel_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if not checked_before or channel_id in checked_before
                else Qt.CheckState.Unchecked
            )
            self.channel_list.addItem(item)
        if self.channel_list.count():
            self.channel_list.setCurrentRow(0)
        selected_group = self.channel_group_combo.currentData()
        self.channel_group_combo.blockSignals(True)
        self.channel_group_combo.clear()
        for group_id, label_key in (
            ("all", "explorer.group.all"),
            ("stable", "explorer.group.stable"),
            ("raw", "explorer.group.raw"),
            ("capability", "explorer.group.capability"),
            ("algorithm", "explorer.group.algorithm"),
        ):
            self.channel_group_combo.addItem(
                self._translator.Text_Get(label_key),
                group_id,
            )
        self.channel_group_combo.setCurrentIndex(
            max(self.channel_group_combo.findData(selected_group), 0)
        )
        self.channel_group_combo.blockSignals(False)
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        record_names = set(dataset.records)
        if dataset.semantic_context is not None:
            for stream in dataset.semantic_context.logging_streams:
                raw_name = str(stream.get("record", ""))
                prefix = "FLIGHT_LOG_RECORD_"
                record_names.add(
                    raw_name[len(prefix) :]
                    if raw_name.startswith(prefix)
                    else raw_name
                )
        self.record_combo.addItems(sorted(name for name in record_names if name))
        self.record_combo.blockSignals(False)
        self._Channels_Filter()
        self._Records_Show()
        self._Diagnostics_Show()

    def _Channels_Filter(self, *_args: object) -> None:
        needle = self.search_edit.text().strip().casefold()
        selected_group = str(self.channel_group_combo.currentData() or "all")
        semantic_context = self._dataset.semantic_context if self._dataset is not None else None
        stable_roles = (
            set(semantic_context.stable_aliases)
            if semantic_context is not None
            else set()
        )
        raw_channel_ids = (
            set(semantic_context.stable_aliases.values())
            if semantic_context is not None
            else set()
        )
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            channel_id = str(item.data(Qt.ItemDataRole.UserRole))
            series = self._channels[channel_id]
            is_algorithm = series.source.startswith("silverstar.algorithm.")
            is_stable = channel_id in stable_roles
            is_raw = channel_id in raw_channel_ids or (
                not is_stable and not is_algorithm
            )
            is_capability = channel_id.split(".", 1)[0] in {
                "imu",
                "gnss",
                "baro",
                "magnetometer",
                "pure_ins",
                "kf6",
            }
            group_matches = {
                "all": True,
                "stable": is_stable,
                "raw": is_raw,
                "capability": is_capability,
                "algorithm": is_algorithm,
            }.get(selected_group, True)
            searchable = " ".join(
                (
                    channel_id,
                    series.quantity,
                    series.unit,
                    series.source,
                    json.dumps(dict(series.metadata), ensure_ascii=False, default=str),
                )
            ).casefold()
            item.setHidden(not group_matches or bool(needle and needle not in searchable))

    def TimeRange_Set(self, start, end):
        self._time_range = (start, end)
        self._Channel_Show(self.channel_list.currentItem())
        self._Records_Show()

    def _Channel_Show(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        channel_id = str(current.data(Qt.ItemDataRole.UserRole))
        series = self._channels.get(channel_id)
        if series is None:
            return
        metadata_text = self._translator.Text_Get(
            "explorer.channel_metadata",
            channel=channel_id,
            quantity=series.quantity,
            unit=series.unit,
            source=series.source,
            count=series.count,
        )
        sampling = Series_SamplingGet(series)
        unavailable = self._translator.Text_Get("explorer.sampling_unavailable")
        metadata_text += "\n" + self._translator.Text_Get(
            "explorer.sampling", count=sampling.sample_count,
            rate=(f"{sampling.measured_rate_hz:.2f} Hz"
                  if sampling.measured_rate_hz is not None else unavailable),
            period=(f"{sampling.median_period_us / 1000:.2f} ms"
                    if sampling.median_period_us is not None else unavailable),
        )
        if self._dataset is not None and self._dataset.semantic_context is not None:
            context = self._dataset.semantic_context
            raw_channel_id = context.StableRole_Get(channel_id)
            semantic_metadata = {
                "stable_role": channel_id if raw_channel_id is not None else None,
                "raw_channel_id": raw_channel_id,
                "series_metadata": dict(series.metadata),
            }
            record_name = series.metadata.get("record_name")
            if isinstance(record_name, str):
                semantic_metadata["record_view"] = context.RecordView_Get(record_name)
                semantic_metadata["logging_stream"] = context.LoggingStream_Get(record_name)
            metadata_text += "\n" + json.dumps(
                semantic_metadata,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        self.channel_metadata.setText(
            metadata_text
        )
        values = np.asarray(series.values)
        value_columns = (
            list(series.columns or tuple(f"value_{index}" for index in range(values.shape[1])))
            if values.ndim == 2
            else ["value"]
        )
        headers = ["timestamp_us", "time_s", *value_columns, "valid"]
        self.channel_table.setColumnCount(len(headers))
        self.channel_table.setHorizontalHeaderLabels(headers)
        origin = (self._dataset.start_timestamp_us or 0) if self._dataset else 0
        indices = np.arange(series.count)
        if self._time_range is not None:
            low, high = self._time_range
            times = (series.timestamp_us.astype(float) - origin) * 1e-6
            indices = indices[(times >= low) & (times <= high)]
        if indices.size:
            indices = indices[DisplayIndices_Get(series.timestamp_us[indices], values[indices],
                                                 series.valid[indices], 5000)]
        self.channel_table.setRowCount(len(indices))
        for row, sample_index in enumerate(indices):
            sample = values[sample_index]
            sample_values = sample.tolist() if values.ndim == 2 else [sample.item()]
            cells = [
                str(int(series.timestamp_us[sample_index])),
                f"{(int(series.timestamp_us[sample_index]) - origin) * 1.0e-6:.9f}",
                *[f"{float(value):.9g}" for value in sample_values],
                str(bool(series.valid[sample_index])),
            ]
            for column, value in enumerate(cells):
                self.channel_table.setItem(row, column, QTableWidgetItem(value))
        header = self.channel_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            self.channel_table.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )

    def _Records_Show(self) -> None:
        if self._dataset is None:
            return
        record_name = self.record_combo.currentText()
        records = self._dataset.Records_Get(record_name)
        fields = sorted({field for record in records for field in record.payload})
        if self._time_range is not None:
            low, high = self._time_range
            origin = self._dataset.start_timestamp_us or 0
            records = tuple(record for record in records
                            if low <= (record.timestamp_us-origin)*1e-6 <= high)
        semantic_context = self._dataset.semantic_context
        if semantic_context is None:
            self.record_metadata.setText("—")
        else:
            metadata = {
                "record_view": semantic_context.RecordView_Get(record_name),
                "logging_stream": semantic_context.LoggingStream_Get(record_name),
            }
            self.record_metadata.setText(
                json.dumps(metadata, ensure_ascii=False, indent=2, default=str)
            )
        headers = [
            "file_offset",
            "timestamp_us",
            "record_sequence",
            "valid_flags",
            *fields,
        ]
        self.record_table.setColumnCount(len(headers))
        self.record_table.setHorizontalHeaderLabels(headers)
        indices = np.unique(np.linspace(0, len(records) - 1, min(len(records), 2000)).astype(int))
        self.record_table.setRowCount(len(indices))
        for row, record_index in enumerate(indices):
            record = records[record_index]
            prefix = [
                record.file_offset,
                record.timestamp_us,
                record.record_sequence,
                record.valid_flags,
            ]
            values = prefix + [record.payload.get(field, "") for field in fields]
            for column, value in enumerate(values):
                if isinstance(value, bytes):
                    text = value.hex(" ")
                elif isinstance(value, (tuple, list, dict)):
                    text = json.dumps(value, ensure_ascii=False)
                else:
                    text = str(value)
                self.record_table.setItem(row, column, QTableWidgetItem(text))
        header = self.record_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            self.record_table.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )

    def _Diagnostics_Show(self) -> None:
        if self._dataset is None:
            return
        diagnostics = self._dataset.diagnostics
        quality = self._dataset.data_quality
        self.diagnostics_summary.setText(
            self._translator.Text_Get(
                "explorer.diagnostics_summary",
                status=(
                    self._translator.Text_Get(
                        f"data_quality.{quality.status.value}"
                    )
                    if quality is not None
                    else self._translator.Text_Get("status.na")
                ),
                crc=diagnostics.record_crc_failures,
                length=diagnostics.record_length_failures,
                resync=diagnostics.resync_count,
                damaged=len(diagnostics.damaged_spans),
                gaps=diagnostics.sequence_gap_count,
                missing=diagnostics.sequence_missing_count,
                unknown=(
                    diagnostics.unknown_record_type_count
                    + diagnostics.unknown_record_version_count
                ),
            )
        )
        gaps = quality.sequence_gaps if quality is not None else ()
        fields = ("expected_sequence", "actual_sequence", "missing_count", "file_offset",
                  "timestamp_us", "mission_phase")
        self.sequence_gap_table.setColumnCount(len(fields))
        self.sequence_gap_table.setHorizontalHeaderLabels([
            self._translator.Text_Get(f"diagnostic.gap.{field}") for field in fields])
        self.sequence_gap_table.setRowCount(len(gaps))
        for row, gap in enumerate(gaps):
            for column, field in enumerate(fields):
                value = gap[field]
                text = (self._translator.Text_Get(f"data_quality.phase.{value}")
                        if field == "mission_phase" else str(value) if value is not None else "—")
                self.sequence_gap_table.setItem(row, column, QTableWidgetItem(text))
        self.sequence_gap_table.resizeColumnsToContents()
        self.sequence_gap_table.setVisible(bool(gaps))
        headers = (
            self._translator.Text_Get("diagnostic.severity"),
            self._translator.Text_Get("diagnostic.code"),
            self._translator.Text_Get("diagnostic.offset"),
            self._translator.Text_Get("diagnostic.sequence"),
            self._translator.Text_Get("diagnostic.details"),
        )
        self.diagnostics_table.setColumnCount(len(headers))
        self.diagnostics_table.setHorizontalHeaderLabels(headers)
        self.diagnostics_table.setRowCount(len(diagnostics.diagnostics))
        for row, diagnostic in enumerate(diagnostics.diagnostics):
            values = (
                diagnostic.severity.value,
                diagnostic.code,
                (
                    str(diagnostic.offset)
                    if diagnostic.offset is not None
                    else "—"
                ),
                (
                    str(diagnostic.record_sequence)
                    if diagnostic.record_sequence is not None
                    else "—"
                ),
                json.dumps(
                    diagnostic.details,
                    ensure_ascii=False,
                    default=str,
                ),
            )
            for column, value in enumerate(values):
                self.diagnostics_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self.diagnostics_table.resizeColumnsToContents()
        self.diagnostics_table.horizontalHeader().setStretchLastSection(True)

    def ExportChannels_Get(self) -> tuple[str, ...]:
        return tuple(
            str(self.channel_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.channel_list.count())
            if self.channel_list.item(index).checkState() == Qt.CheckState.Checked
        )

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        selected_group = self.channel_group_combo.currentData()
        self.channel_group_combo.blockSignals(True)
        for index, label_key in enumerate(
            (
                "explorer.group.all",
                "explorer.group.stable",
                "explorer.group.raw",
                "explorer.group.capability",
                "explorer.group.algorithm",
            )
        ):
            if index < self.channel_group_combo.count():
                self.channel_group_combo.setItemText(index, translator.Text_Get(label_key))
        self.channel_group_combo.setCurrentIndex(
            max(self.channel_group_combo.findData(selected_group), 0)
        )
        self.channel_group_combo.blockSignals(False)
        self.search_edit.setPlaceholderText(translator.Text_Get("explorer.filter_channels"))
        self.display_note.setText(translator.Text_Get("explorer.display_note"))
        self.record_type_label.setText(translator.Text_Get("explorer.record_type"))
        self.tabs.setTabText(0, translator.Text_Get("explorer.channels"))
        self.tabs.setTabText(1, translator.Text_Get("explorer.decoded_records"))
        self.tabs.setTabText(2, translator.Text_Get("explorer.diagnostics"))
        self._Channel_Show(self.channel_list.currentItem())
        self._Diagnostics_Show()
