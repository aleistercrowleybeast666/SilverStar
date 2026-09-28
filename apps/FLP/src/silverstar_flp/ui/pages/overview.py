from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.analysis.overview import (
    AlignmentOverview,
    CalibrationOverview,
    DeployOverview,
    FlightSummary_Build,
    GnssOverview,
)
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable


class _MetricCard(QGroupBox):
    def __init__(self, title: str) -> None:
        super().__init__(title)
        layout = QVBoxLayout(self)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("metricValue")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("muted")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)


def _Status_Apply(widget: QWidget, level: str) -> None:
    widget.setProperty("statusLevel", level)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class OverviewPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._dataset: FlightDataset | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        TouchScroll_Enable(self.scroll_area)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 14)
        layout.setSpacing(10)

        self.summary_group = QGroupBox()
        summary_layout = QVBoxLayout(self.summary_group)
        self.file_label = QLabel(translator.Text_Get("status.no_data"))
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.file_label)
        layout.addWidget(self.summary_group)

        metrics = QGridLayout()
        self.duration_card = _MetricCard(translator.Text_Get("label.duration"))
        self.altitude_card = _MetricCard(translator.Text_Get("label.max_altitude"))
        self.speed_card = _MetricCard(translator.Text_Get("label.max_speed"))
        self.acceleration_card = _MetricCard(translator.Text_Get("label.max_acceleration"))
        self.deploy_card = _MetricCard(translator.Text_Get("label.deploy_altitude"))
        self.gnss_card = _MetricCard(translator.Text_Get("label.gnss_status"))
        self.quality_card = _MetricCard(translator.Text_Get("label.data_quality"))
        cards = (
            self.duration_card,
            self.altitude_card,
            self.speed_card,
            self.acceleration_card,
            self.deploy_card,
            self.gnss_card,
            self.quality_card,
        )
        for index, card in enumerate(cards):
            metrics.addWidget(card, index // 3, index % 3)
        layout.addLayout(metrics)

        result_row = QHBoxLayout()
        result_row.setSpacing(10)
        self.calibration_group = QGroupBox()
        calibration_layout = QVBoxLayout(self.calibration_group)
        self.calibration_summary = QGridLayout()
        self.calibration_value_labels: dict[str, QLabel] = {}
        for row, field in enumerate(
            ("configured", "mode", "status", "faces", "samples", "rejected", "retries")
        ):
            title = QLabel()
            title.setObjectName("muted")
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.calibration_summary.addWidget(title, row // 2, (row % 2) * 2)
            self.calibration_summary.addWidget(value, row // 2, (row % 2) * 2 + 1)
            self.calibration_value_labels[field] = value
            setattr(self, f"calibration_{field}_title", title)
        calibration_layout.addLayout(self.calibration_summary)
        self.calibration_model_table = QTableWidget(4, 5)
        TouchScroll_Enable(self.calibration_model_table)
        self.calibration_model_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.calibration_model_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.calibration_model_table.verticalHeader().setVisible(False)
        self.calibration_model_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 5):
            self.calibration_model_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.calibration_model_table.setMinimumHeight(190)
        calibration_layout.addWidget(self.calibration_model_table)
        self.calibration_note = QLabel()
        self.calibration_note.setObjectName("muted")
        self.calibration_note.setWordWrap(True)
        calibration_layout.addWidget(self.calibration_note)
        result_row.addWidget(self.calibration_group, 1)

        self.alignment_group = QGroupBox()
        alignment_layout = QVBoxLayout(self.alignment_group)
        self.alignment_summary = QGridLayout()
        self.alignment_value_labels: dict[str, QLabel] = {}
        for row, field in enumerate(
            ("mode", "status", "known_yaw", "declination", "samples", "used")
        ):
            title = QLabel()
            title.setObjectName("muted")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.alignment_summary.addWidget(title, row, 0)
            self.alignment_summary.addWidget(value, row, 1)
            self.alignment_value_labels[field] = value
            setattr(self, f"alignment_{field}_title", title)
        alignment_layout.addLayout(self.alignment_summary)
        self.alignment_q_title = QLabel()
        self.alignment_q_title.setObjectName("muted")
        alignment_layout.addWidget(self.alignment_q_title)
        self.alignment_q_table = QTableWidget(1, 4)
        TouchScroll_Enable(self.alignment_q_table)
        self.alignment_q_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.alignment_q_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.alignment_q_table.verticalHeader().setVisible(False)
        self.alignment_q_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.alignment_q_table.setMaximumHeight(86)
        alignment_layout.addWidget(self.alignment_q_table)
        self.alignment_note = QLabel()
        self.alignment_note.setObjectName("muted")
        self.alignment_note.setWordWrap(True)
        alignment_layout.addWidget(self.alignment_note)
        result_row.addWidget(self.alignment_group, 1)
        layout.addLayout(result_row)

        self.timeline_group = QGroupBox(translator.Text_Get("label.timeline"))
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline_table = QTableWidget(0, 4)
        TouchScroll_Enable(self.timeline_table)
        self.timeline_table.setMinimumHeight(260)
        self.timeline_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        timeline_layout.addWidget(self.timeline_table)
        layout.addWidget(self.timeline_group)
        layout.addStretch(1)

        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        self.Language_Apply(translator)

    def Dataset_Set(self, dataset: FlightDataset) -> None:
        self._dataset = dataset
        summary = FlightSummary_Build(dataset)
        synthetic = (
            f" · {self._translator.Text_Get('status.synthetic')}" if summary.synthetic else ""
        )
        start_note = (
            f" · {self._translator.Text_Get('overview.start_fallback')}"
            if summary.start_fallback
            else ""
        )
        self.file_label.setText(
            f"{dataset.source_path} · SSLOG0 · "
            f"{self._translator.Text_Get('overview.recorded_navigation')}: "
            f"{summary.source_name}{synthetic}{start_note}"
        )
        if dataset.semantic_context is not None:
            context = dataset.semantic_context
            identity = context.PackageIdentity_Get()
            self.file_label.setText(
                self.file_label.text()
                + "\n"
                + self._translator.Text_Get(
                    "overview.decoder_identity",
                    project=context.Project_Get(),
                    firmware=context.FirmwareVersion_Get(),
                    package_hash=identity.package_sha256,
                    generation_hash=identity.generation_profile_sha256,
                )
            )
        self.duration_card.value_label.setText(
            f"{summary.duration_s:.3f} s" if summary.duration_s is not None else "—"
        )
        self.altitude_card.value_label.setText(
            f"{summary.maximum_altitude_m:.3f} m" if summary.maximum_altitude_m is not None else "—"
        )
        self.speed_card.value_label.setText(
            f"{summary.maximum_speed_mps:.3f} m/s" if summary.maximum_speed_mps is not None else "—"
        )
        self.acceleration_card.value_label.setText(
            f"{summary.maximum_acceleration_mps2:.3f} m/s²"
            if summary.maximum_acceleration_mps2 is not None
            else "—"
        )
        self._Deploy_Set(summary.deploy)
        self._Gnss_Set(summary.gnss)
        self.quality_card.value_label.setText(
            self._translator.Text_Get(
                f"data_quality.{summary.data_quality.status.value}"
            )
        )
        self.quality_card.detail_label.setText(
            self._translator.Text_Get(
                "overview.quality_detail",
                records=summary.data_quality.valid_record_count,
                crc=summary.data_quality.crc_failure_count,
                length=summary.data_quality.length_failure_count,
                resync=summary.data_quality.resync_count,
                gaps=summary.data_quality.sequence_gap_count,
                unknown=summary.data_quality.unknown_record_count,
                decoder=summary.data_quality.decoder_failure_count,
                overflow=(summary.data_quality.logger_overflow_count
                          if summary.data_quality.logger_overflow_count is not None else "—"),
                imu_overflow=(summary.data_quality.imu_queue_overflow_count
                              if summary.data_quality.imu_queue_overflow_count is not None
                              else "—"),
                missing=summary.data_quality.sequence_missing_count,
                integrity=self._translator.Text_Get(
                    f"data_quality.integrity.{summary.data_quality.structural_integrity}"),
                continuity=self._translator.Text_Get(
                    f"data_quality.continuity.{summary.data_quality.mission_record_continuity}"),
            )
        )
        _Status_Apply(
            self.quality_card,
            (
                "success"
                if summary.data_quality.status.value == "clean"
                else "warning"
            ),
        )
        self._Calibration_Set(summary.calibration)
        self._Alignment_Set(summary.alignment)
        start = summary.mission_start_timestamp_us or (
            summary.timeline[0].timestamp_us if summary.timeline else 0
        )
        self.timeline_table.setRowCount(len(summary.timeline))
        for row, event in enumerate(summary.timeline):
            event_code = f"event.{event.name}"
            event_text = self._translator.Text_Get(event_code)
            if event_text == event_code:
                event_text = event.name
            values = (
                f"{(event.timestamp_us - start) * 1.0e-6:.6f}",
                event_text,
                str(event.arg0),
                str(event.arg1),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(event.name)
                if event.name == "MISSION_START":
                    item.setBackground(QColor("#2563EB"))
                    item.setForeground(QColor("#FFFFFF"))
                elif event.name in ("CALIBRATION_FAILED", "ALIGNMENT_FAILED", "SYSTEM_FAULT"):
                    item.setBackground(QColor("#B91C1C"))
                    item.setForeground(QColor("#FFFFFF"))
                self.timeline_table.setItem(row, column, item)
        self.timeline_table.resizeColumnsToContents()

    def _Gnss_Set(self, gnss: GnssOverview) -> None:
        if not gnss.native_configured and not gnss.measurement_configured:
            value_code = "gnss.not_configured"
            status_level = "neutral"
        elif gnss.latest_online is None:
            value_code = "gnss.configured_no_samples"
            status_level = "warning"
        elif not gnss.latest_online:
            value_code = "gnss.offline"
            status_level = "warning"
        elif gnss.latest_fix_type in (None, 0) or gnss.position_usable_count == 0:
            value_code = "gnss.online_no_fix"
            status_level = "warning"
        else:
            value_code = "gnss.online_fixed"
            status_level = "success"
        self.gnss_card.value_label.setText(
            self._translator.Text_Get(value_code)
        )
        self.gnss_card.detail_label.setText(
            self._translator.Text_Get(
                "gnss.detail",
                native=gnss.native_sample_count,
                measurements=gnss.measurement_sample_count,
                position=gnss.position_usable_count,
                velocity=gnss.velocity_usable_count,
            )
        )
        _Status_Apply(self.gnss_card, status_level)

    def _Deploy_Set(self, deploy: DeployOverview) -> None:
        self.deploy_card.value_label.setText(
            f"{deploy.altitude_m:.3f} m" if deploy.altitude_m is not None else "—"
        )
        details: list[str] = []
        if deploy.altitude_m is not None:
            details.append(
                self._translator.Text_Get("overview.deploy_source", source=deploy.altitude_source)
            )
        if deploy.timestamp_us is None:
            details.append(self._translator.Text_Get("overview.deploy_not_recorded"))
        elif not deploy.actual_reason_recorded:
            details.append(self._translator.Text_Get("overview.deploy_reason_unrecorded"))
            enabled = self._TriggerMask_Text(deploy.enabled_trigger_mask)
            if enabled:
                details.append(
                    self._translator.Text_Get("overview.enabled_triggers", values=enabled)
                )
        else:
            reasons = self._TriggerMask_Text(deploy.actual_trigger_mask)
            details.append(self._translator.Text_Get("overview.deploy_reason", values=reasons))
            value = self._TriggerValue_Text(deploy)
            if value:
                details.append(value)
        self.deploy_card.detail_label.setText("\n".join(details))

    def _TriggerMask_Text(self, mask: int) -> str:
        names: list[str] = []
        for bit, code in (
            (0x01, "deploy.trigger.tilt"),
            (0x02, "deploy.trigger.apogee_vz"),
            (0x04, "deploy.trigger.delay"),
        ):
            if mask & bit:
                names.append(self._translator.Text_Get(code))
        return " + ".join(names)

    def _TriggerValue_Text(self, deploy: DeployOverview) -> str:
        if deploy.trigger_value is None:
            return ""
        if deploy.trigger_threshold is None:
            code = {
                "vertical_velocity": "deploy.value.vertical_velocity",
                "tilt_angle": "deploy.value.tilt",
                "mission_delay": "deploy.value.delay",
            }.get(deploy.trigger_value_kind)
            return (
                self._translator.Text_Get(code, value=deploy.trigger_value)
                if code is not None
                else ""
            )
        if deploy.trigger_value_kind == "vertical_velocity":
            return self._translator.Text_Get(
                "deploy.detail.vertical_velocity",
                value=deploy.trigger_value,
                threshold=deploy.trigger_threshold,
            )
        if deploy.trigger_value_kind == "tilt_angle":
            return self._translator.Text_Get(
                "deploy.detail.tilt",
                value=deploy.trigger_value,
                threshold=deploy.trigger_threshold,
            )
        if deploy.trigger_value_kind == "mission_delay":
            return self._translator.Text_Get(
                "deploy.detail.delay",
                value=deploy.trigger_value,
                threshold=deploy.trigger_threshold,
            )
        return ""

    def _Calibration_Set(self, calibration: CalibrationOverview) -> None:
        mode_codes = {
            0: "calibration.mode.none",
            1: "calibration.mode.one_face",
            2: "calibration.mode.six_face",
            0xFF: "calibration.mode.not_selected",
        }
        if not calibration.present:
            values = {
                field: self._translator.Text_Get("status.na")
                for field in self.calibration_value_labels
            }
            status_level = "neutral"
        else:
            mode_code = mode_codes.get(calibration.mode, "calibration.mode.unknown")
            if calibration.ready:
                status_code = "status.ready"
                status_level = "success"
            elif calibration.state == 5:
                status_code = "status.failed"
                status_level = "error"
            else:
                status_code = "status.incomplete"
                status_level = "warning"
            faces = (
                f"{calibration.completed_faces} / {calibration.required_faces}"
                if calibration.required_faces
                else self._translator.Text_Get("status.na")
            )
            values = {
                "configured": (
                    " / ".join(calibration.configured_modes)
                    if calibration.configured_modes
                    else self._translator.Text_Get("calibration.configured_none")
                ),
                "mode": self._translator.Text_Get(mode_code),
                "status": self._translator.Text_Get(status_code),
                "faces": faces,
                "samples": str(calibration.samples),
                "rejected": str(calibration.reject_count),
                "retries": str(calibration.retry_count),
            }
        for field, value in values.items():
            self.calibration_value_labels[field].setText(value)
        self.calibration_note.setText(
            self._translator.Text_Get(
                "calibration.none_identity_note"
                if calibration.present and calibration.mode == 0
                else "calibration.corrected_imu_note"
            )
        )
        _Status_Apply(self.calibration_group, status_level)
        dimensionless = self._translator.Text_Get("unit.dimensionless")
        model_rows = (
            ("calibration.accel_bias", calibration.accel_bias_mps2, "m/s²"),
            ("calibration.accel_scale", calibration.accel_scale, dimensionless),
            ("calibration.gyro_bias", calibration.gyro_bias_radps, "rad/s"),
            ("calibration.gyro_scale", calibration.gyro_scale, dimensionless),
        )
        for row, (code, vector, unit) in enumerate(model_rows):
            row_values = [
                self._translator.Text_Get(code),
                *([f"{value:.8g}" for value in vector] if vector is not None else ["—"] * 3),
                unit,
            ]
            for column, value in enumerate(row_values):
                self.calibration_model_table.setItem(row, column, QTableWidgetItem(value))

    def _Alignment_Set(self, alignment: AlignmentOverview) -> None:
        mode_codes = {
            0: "alignment.mode.hw_6axis_known_yaw",
            1: "alignment.mode.gravity_mag_triad",
            2: "alignment.mode.hw_9axis",
            3: "alignment.mode.gravity_known_yaw",
        }
        if not alignment.present:
            values = {
                field: self._translator.Text_Get("status.na")
                for field in self.alignment_value_labels
            }
            status_level = "neutral"
        else:
            if alignment.state == 5:
                status_code = "status.stale"
                status_level = "warning"
            elif alignment.ready or alignment.state == 3:
                status_code = "status.ready"
                status_level = "success"
            elif alignment.state == 4:
                status_code = "status.failed"
                status_level = "error"
            else:
                status_code = "status.incomplete"
                status_level = "warning"
            used = ", ".join(
                self._translator.Text_Get(f"alignment.source.{source}")
                for source in alignment.used_sources
            )
            values = {
                "mode": self._translator.Text_Get(
                    mode_codes.get(alignment.mode, "alignment.mode.unknown")
                ),
                "status": self._translator.Text_Get(status_code),
                "known_yaw": (
                    f"{alignment.known_yaw_deg:.2f}°"
                    if alignment.known_yaw_deg is not None
                    else self._translator.Text_Get("status.na")
                ),
                "declination": (
                    f"{alignment.magnetic_declination_deg:.2f}°"
                    if alignment.magnetic_declination_deg is not None
                    else self._translator.Text_Get("status.na")
                ),
                "samples": (
                    str(alignment.sample_count)
                    if alignment.sample_count is not None
                    else self._translator.Text_Get("status.na")
                ),
                "used": used or self._translator.Text_Get("status.na"),
            }
        for field, value in values.items():
            self.alignment_value_labels[field].setText(value)
        _Status_Apply(self.alignment_group, status_level)
        quaternion = alignment.q_nb or (None, None, None, None)
        for column, value in enumerate(quaternion):
            text = f"{value:.8g}" if value is not None else "—"
            self.alignment_q_table.setItem(0, column, QTableWidgetItem(text))
        notes: list[str] = [
            self._translator.Text_Get(
                "alignment.quaternion_source",
                record=alignment.quaternion_record or self._translator.Text_Get("status.na"),
            )
        ]
        if alignment.historical_mode:
            notes.append(self._translator.Text_Get("alignment.historical"))
        notes.append(
            self._translator.Text_Get(
                "alignment.history",
                count=alignment.history_count,
                ready=alignment.ready_history_count,
            )
        )
        if alignment.initial_state_authoritative:
            notes.append(
                self._translator.Text_Get("alignment.initial_state_authoritative")
            )
        self.alignment_note.setText(" · ".join(notes))

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.summary_group.setTitle(translator.Text_Get("overview.mission_summary"))
        self.duration_card.setTitle(translator.Text_Get("label.duration"))
        self.altitude_card.setTitle(translator.Text_Get("label.max_altitude"))
        self.speed_card.setTitle(translator.Text_Get("label.max_speed"))
        self.acceleration_card.setTitle(translator.Text_Get("label.max_acceleration"))
        self.deploy_card.setTitle(translator.Text_Get("label.deploy_altitude"))
        self.gnss_card.setTitle(translator.Text_Get("label.gnss_status"))
        self.quality_card.setTitle(translator.Text_Get("label.data_quality"))
        self.calibration_group.setTitle(translator.Text_Get("label.calibration"))
        calibration_titles = {
            "configured": "calibration.configured_flow",
            "mode": "label.mode",
            "status": "label.status",
            "faces": "calibration.faces",
            "samples": "label.samples",
            "rejected": "calibration.rejected",
            "retries": "calibration.retries",
        }
        for field, code in calibration_titles.items():
            getattr(self, f"calibration_{field}_title").setText(
                f"{translator.Text_Get(code)}:"
            )
        self.calibration_model_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("label.model"),
                "X",
                "Y",
                "Z",
                translator.Text_Get("label.unit"),
            ]
        )
        self.calibration_group.setToolTip(translator.Text_Get("calibration.corrected_imu_tooltip"))

        self.alignment_group.setTitle(translator.Text_Get("label.initial_alignment"))
        alignment_titles = {
            "mode": "label.mode",
            "status": "label.status",
            "known_yaw": "alignment.known_yaw",
            "declination": "alignment.declination",
            "samples": "label.samples",
            "used": "alignment.used",
        }
        for field, code in alignment_titles.items():
            getattr(self, f"alignment_{field}_title").setText(
                f"{translator.Text_Get(code)}:"
            )
        self.alignment_known_yaw_title.setToolTip(
            translator.Text_Get("alignment.known_yaw_tooltip")
        )
        self.alignment_value_labels["known_yaw"].setToolTip(
            translator.Text_Get("alignment.known_yaw_tooltip")
        )
        self.alignment_q_title.setText(translator.Text_Get("alignment.q_nb_title"))
        self.alignment_q_table.setHorizontalHeaderLabels(("W", "X", "Y", "Z"))

        self.timeline_group.setTitle(translator.Text_Get("label.timeline"))
        self.timeline_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("timeline.time"),
                translator.Text_Get("timeline.event"),
                "arg0",
                "arg1",
            ]
        )
        if self._dataset is not None:
            self.Dataset_Set(self._dataset)
