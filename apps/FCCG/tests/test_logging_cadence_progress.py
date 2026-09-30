from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QSpinBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.view_models import LoggingStreamView
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.lifecycle import ProjectLifecycleState
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LogCadenceKind,
    ProjectProtocolLogMetadataPath_Get,
    ProtocolLogDefinitions_Get,
    ProtocolLogDefinitions_Load,
)
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.pages.components import CadenceEditor
from silverstar_fccg.ui.widgets import StandardCheckBox


def _StreamRow_Get(window: MainWindow, stream_id: str) -> int:
    table = window.flight_configuration_page.logging_table
    for row in range(table.rowCount()):
        container = table.cellWidget(row, 0)
        check = container.findChild(StandardCheckBox) if container else None
        if check is not None and check.property("streamId") == stream_id:
            return row
    raise AssertionError(f"Logging row not found: {stream_id}")


def test_logging_metadata_declares_cadence_and_legacy_policy_fallback(
    tmp_path: Path,
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("Cadence", catalog=builtin_catalog)
    definitions = {
        definition.record: definition
        for definition in ProtocolLogDefinitions_Get(model, builtin_catalog)
    }
    assert len(definitions) == 38
    assert definitions[
        "FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR"
    ].cadence.kind == "one_shot"
    metadata_path = ProjectProtocolLogMetadataPath_Get(model, builtin_catalog)
    parser_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    record_catalog = json.loads(
        (metadata_path.parent / "sslog_schema.json").read_text(encoding="utf-8")
    )
    for catalog_record, parser_record in zip(
        record_catalog["records"], parser_metadata["records"], strict=True
    ):
        assert parser_record["default_stream"] == catalog_record["default_stream"]
    assert definitions["FLIGHT_LOG_RECORD_IMU_CORRECTED"].default_stream.enabled
    assert definitions["FLIGHT_LOG_RECORD_MAG_NATIVE"].default_stream.enabled
    assert not definitions["FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC"].default_stream.enabled
    assert not next(stream.enabled for stream in model.logging_streams
                    if stream.record == "FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC")
    assert definitions["FLIGHT_LOG_RECORD_IMU_CORRECTED"].cadence == replace(
        definitions["FLIGHT_LOG_RECORD_IMU_CORRECTED"].cadence,
        kind=LogCadenceKind.SOURCE,
        source="imu",
    )
    assert (
        definitions["FLIGHT_LOG_RECORD_IMU_CORRECTED"].cadence.DisplayName_Get(
            "zh_CN"
        )
        == "取决于IMU数据更新"
    )
    assert definitions["FLIGHT_LOG_RECORD_GNSS_MEASUREMENT"].cadence.kind == (
        LogCadenceKind.MEASUREMENT
    )
    assert definitions["FLIGHT_LOG_RECORD_EVENT"].cadence.kind == (
        LogCadenceKind.EVENT
    )
    assert definitions["FLIGHT_LOG_RECORD_SYSTEM_CONFIG"].cadence.kind == (
        LogCadenceKind.ONE_SHOT
    )
    assert definitions["FLIGHT_LOG_RECORD_STATS"].default_stream.period_us == (
        1_000_000
    )
    assert definitions[
        "FLIGHT_LOG_RECORD_TELEMETRY_DIAG"
    ].default_stream.period_us == 1_000_000
    assert definitions["FLIGHT_LOG_RECORD_STATS"].producer_components == (
        "silverstar.core.device_task",
    )
    assert definitions[
        "FLIGHT_LOG_RECORD_TELEMETRY_DIAG"
    ].producer_components == ("silverstar.core.telemetry_task",)
    assert LogAvailability_Get(
        definitions["FLIGHT_LOG_RECORD_STATS"], model, builtin_catalog
    ).available
    assert LogAvailability_Get(
        definitions["FLIGHT_LOG_RECORD_TELEMETRY_DIAG"],
        model,
        builtin_catalog,
    ).available
    core = builtin_catalog.Component_Get("silverstar.core.0_1_0")
    assert "log_producers" not in core.metadata
    assert core.metadata["protocol_log_producers"] == {
        "logging": [
            "silverstar.core.device_task",
            "silverstar.core.flight_task",
        ],
        "telemetry": ["silverstar.core.telemetry_task"],
    }
    streams = {stream.record: stream for stream in model.logging_streams}
    assert streams["FLIGHT_LOG_RECORD_STATS"].enabled
    assert streams["FLIGHT_LOG_RECORD_STATS"].period_us == 1_000_000
    assert streams["FLIGHT_LOG_RECORD_TELEMETRY_DIAG"].enabled
    assert streams["FLIGHT_LOG_RECORD_TELEMETRY_DIAG"].period_us == 1_000_000

    records = []
    expected = {
        "PERIODIC": LogCadenceKind.PERIODIC,
        "DECIMATION": LogCadenceKind.SOURCE,
        "EVERY": LogCadenceKind.MEASUREMENT,
        "EVENT": LogCadenceKind.EVENT,
        "ONE_SHOT": LogCadenceKind.ONE_SHOT,
    }
    for index, policy in enumerate(expected, start=1):
        records.append(
            {
                "enum": f"FLIGHT_LOG_RECORD_LEGACY_{policy}",
                "name": f"LEGACY_{policy}",
                "id": str(index),
                "version": 0,
                "payload_size": 1,
                "default_stream": {
                    "enabled": False,
                    "policy": policy,
                    "decimation": 1,
                    "period_us": 0,
                },
            }
        )
    legacy_path = tmp_path / "legacy_logging_metadata.json"
    legacy_path.write_text(
        json.dumps({"records": records, "fccg": {"records": {record["enum"]: {"purpose": "flight"} for record in records}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    legacy = ProtocolLogDefinitions_Load(legacy_path)

    assert {
        definition.default_stream.policy: definition.cadence.kind
        for definition in legacy
    } == expected


def test_logging_gui_uses_semantic_cadence_and_preserves_microseconds(
    tmp_path: Path,
    qapp,
) -> None:
    service = FccgService(Path(__file__).resolve().parents[1])
    window = MainWindow(
        SettingsStore(tmp_path / "settings.ini"),
        service=service,
        language="zh_CN",
    )
    window.show()
    qapp.processEvents()
    try:
        table = window.flight_configuration_page.logging_table
        assert table.horizontalHeaderItem(5).text() == "周期"

        stats_row = _StreamRow_Get(window, "FLIGHT_LOG_RECORD_STATS")
        stats_cadence = table.cellWidget(stats_row, 5)
        assert isinstance(stats_cadence, CadenceEditor)
        assert stats_cadence.PeriodUs_Get() == 1_000_000
        assert not stats_cadence.value_spin.isHidden()
        assert stats_cadence.unit_combo.currentData() == "s"

        semantic_rows = {
            "FLIGHT_LOG_RECORD_IMU_CORRECTED": "取决于IMU数据更新",
            "FLIGHT_LOG_RECORD_GNSS_MEASUREMENT": "每次相关量测",
            "FLIGHT_LOG_RECORD_EVENT": "取决于相关事件",
            "FLIGHT_LOG_RECORD_SYSTEM_CONFIG": "一次性",
        }
        for stream_id, expected_text in semantic_rows.items():
            row = _StreamRow_Get(window, stream_id)
            cadence = table.cellWidget(row, 5)
            assert isinstance(cadence, CadenceEditor)
            assert cadence.value_spin.isHidden()
            assert cadence.text_label.text() == expected_text
            assert "0 us" not in cadence.text_label.text()

        decimation_row = _StreamRow_Get(
            window, "FLIGHT_LOG_RECORD_MAG_NATIVE"
        )
        decimation_editor = table.cellWidget(decimation_row, 4)
        assert isinstance(decimation_editor, QSpinBox)
        assert decimation_editor.prefix() == "每 "
        assert decimation_editor.suffix() == " 次记录 1 次"
        assert decimation_editor.toolTip() == "每 N 次数据更新记录 1 次"
        for stream_id in (
            "FLIGHT_LOG_RECORD_IMU_CORRECTED",
            "FLIGHT_LOG_RECORD_INERTIAL_INCREMENT",
            "FLIGHT_LOG_RECORD_GNSS_NATIVE",
            "FLIGHT_LOG_RECORD_BARO_NATIVE",
            "FLIGHT_LOG_RECORD_STATS",
            "FLIGHT_LOG_RECORD_EVENT",
            "FLIGHT_LOG_RECORD_SYSTEM_CONFIG",
            "FLIGHT_LOG_RECORD_GNSS_MEASUREMENT",
        ):
            row = _StreamRow_Get(window, stream_id)
            assert table.cellWidget(row, 4) is None
            assert table.item(row, 4).text() == "—"

        stats_cadence.unit_combo.setCurrentIndex(
            stats_cadence.unit_combo.findData("ms")
        )
        assert stats_cadence.PeriodUs_Get() == 1_000_000
        stats_cadence.value_spin.setValue(500)
        QTest.keyClick(stats_cadence.value_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        stream = next(
            stream
            for stream in window._model.logging_streams
            if stream.record == "FLIGHT_LOG_RECORD_STATS"
        )
        assert stream.period_us == 500_000
        assert window._project_state == ProjectLifecycleState.DIRTY

        project_file = tmp_path / "Cadence.ssproject"
        ProjectModel_Save(window._model, project_file, WorkspacePolicy(tmp_path))
        saved = ProjectModel_Load(project_file)
        assert next(
            stream.period_us
            for stream in saved.logging_streams
            if stream.record == "FLIGHT_LOG_RECORD_STATS"
        ) == 500_000

        window.Language_Apply("en_US")
        assert table.horizontalHeaderItem(5).text() == "Cadence"
        assert table.horizontalHeaderItem(4).text() == "Decimation Factor"
    finally:
        window.close()
        qapp.processEvents()


def test_logging_bulk_selection_respects_availability_and_configuration_refresh(
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(
        SettingsStore(tmp_path / "logging-selection.ini"),
        language="zh_CN",
    )
    qapp.processEvents()
    try:
        page = window.flight_configuration_page
        assert page.logging_select_all_button.text() == "打开全部"
        assert page.logging_required_only_button.text() == "只留必须"
        assert (
            page.logging_select_all_button.objectName()
            == "loggingEnableAllButton"
        )
        assert (
            page.logging_required_only_button.objectName()
            == "loggingKeepRequiredOnlyButton"
        )
        required_view = next(
            stream for stream in page._streams if stream.required
        )
        required_row = _StreamRow_Get(window, required_view.stream_id)
        assert page.logging_table.item(required_row, 2).text() == "飞行"
        assert page.logging_table.item(required_row, 3).text() == "必须"

        logging_settings = {
            stream.record: (
                stream.policy,
                stream.decimation,
                stream.period_us,
            )
            for stream in window._model.logging_streams
        }
        unrelated_configuration = (
            window._model.ComponentIds_Get(),
            deepcopy(window._model.strategies),
            deepcopy(window._model.modes),
            deepcopy(window._model.protocols),
            deepcopy(window._model.resource_assignments),
        )

        page.logging_required_only_button.click()
        qapp.processEvents()
        views = {stream.stream_id: stream for stream in page._streams}
        streams = {
            stream.record: stream for stream in window._model.logging_streams
        }
        assert any(
            view.available and not view.required for view in views.values()
        )
        assert all(
            streams[record].enabled == (view.required and view.available)
            for record, view in views.items()
        )
        assert {
            stream.record: (
                stream.policy,
                stream.decimation,
                stream.period_us,
            )
            for stream in window._model.logging_streams
        } == logging_settings
        assert (
            window._model.ComponentIds_Get(),
            window._model.strategies,
            window._model.modes,
            window._model.protocols,
            window._model.resource_assignments,
        ) == unrelated_configuration

        page.logging_select_all_button.click()
        qapp.processEvents()
        views = {stream.stream_id: stream for stream in page._streams}
        streams = {
            stream.record: stream for stream in window._model.logging_streams
        }
        assert any(not view.available for view in views.values())
        assert all(
            streams[record].enabled == view.available
            for record, view in views.items()
        )

        page.logging_required_only_button.click()
        qapp.processEvents()
        assert any(
            not stream.enabled
            for stream in window._model.logging_streams
            if views[stream.record].available
            and not views[stream.record].required
        )

        window._Strategy_Change("estimator", None)
        qapp.processEvents()
        definitions = ProtocolLogDefinitions_Get(
            window._model, window._service.catalog
        )
        streams = {
            stream.record: stream for stream in window._model.logging_streams
        }
        views = {stream.stream_id: stream for stream in page._streams}
        assert all(
            streams[definition.record].enabled
            == (definition.level == "required" and views[definition.record].available)
            for definition in definitions
        )

        window.Language_Apply("en_US")
        assert page.logging_select_all_button.text() == "Enable All"
        assert page.logging_required_only_button.text() == "Required Only"
    finally:
        window.close()
        qapp.processEvents()


def test_log_decoder_export_button_writes_verified_profile_without_dirtying_project(
    tmp_path: Path,
    qapp,
    monkeypatch,
) -> None:
    service = FccgService(Path(__file__).resolve().parents[1])
    model = service.ReferenceProject_Create("DecoderExport")
    project_root = tmp_path / "project"
    service.ProjectRoot_Save(model, project_root)
    TargetGeneration_Apply(
        model,
        service.catalog,
        WorkspacePolicy(service.workspace_root),
        project_root,
        TargetScope.FLIGHT,
    )
    window = MainWindow(
        SettingsStore(tmp_path / "settings.ini"),
        service=service,
        language="zh_CN",
    )
    window._model = service.Project_Open(project_root)
    window._project_root = project_root
    window._project_state = ProjectLifecycleState.READY
    window._Project_Refresh()
    window.show()
    qapp.processEvents()
    destination = tmp_path / "exported.ssdecoder"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_arguments, **_keywords: (str(destination), ""),
    )
    monkeypatch.setattr(
        window,
        "Task_Run",
        lambda *_arguments, **_keywords: (_ for _ in ()).throw(
            AssertionError("decoder-profile export must not start a background task")
        ),
    )
    monkeypatch.setattr(
        window,
        "_Error_Show",
        lambda error: (_ for _ in ()).throw(AssertionError(str(error))),
    )
    try:
        before_model = deepcopy(window._model.Dictionary_Get())
        before_state = window._project_state
        generated = project_root / "DecoderExport.ssdecoder"

        window.flight_configuration_page.log_decoder_export_button.click()

        assert destination.read_bytes() == generated.read_bytes()
        assert window._model.Dictionary_Get() == before_model
        assert window._project_state == before_state
        assert window.status_label.text() == (
            f"日志解析配置包已导出：{destination}"
        )
        assert window._active_worker is None
        assert (
            window.flight_configuration_page.log_decoder_export_button.text()
            == "导出日志解析配置包"
        )

        window.Language_Apply("en_US")
        assert (
            window.flight_configuration_page.log_decoder_export_button.text()
            == "Export Log Decoder Profile"
        )

        stale_model = deepcopy(window._model)
        stale_model.logging_streams[0] = replace(
            stale_model.logging_streams[0],
            enabled=not stale_model.logging_streams[0].enabled,
        )
        with pytest.raises(FccgError) as stale_error:
            service.LogDecoderProfile_Export(
                stale_model,
                project_root,
                tmp_path / "stale.ssdecoder",
            )
        assert stale_error.value.code == (
            "error.log_decoder_profile_project_not_ready"
        )
        assert not (tmp_path / "stale.ssdecoder").exists()
    finally:
        window.close()
        qapp.processEvents()


def test_declared_log_producer_is_required_but_legacy_metadata_is_permissive(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("Producer", catalog=builtin_catalog)
    base = next(
        definition
        for definition in ProtocolLogDefinitions_Get(model, builtin_catalog)
        if definition.record == "FLIGHT_LOG_RECORD_EVENT"
    )
    unconstrained = replace(
        base,
        capabilities_required=(),
        recordable_capabilities_required=(),
        components_required=(),
        strategy_slots_required=(),
    )
    assert LogAvailability_Get(unconstrained, model, builtin_catalog).available

    missing = replace(
        unconstrained,
        producer_components=("silverstar.test.missing_producer",),
    )
    unavailable = LogAvailability_Get(missing, model, builtin_catalog)
    assert not unavailable.available
    assert unavailable.reason_code == "logging.unavailable.producer"

    selected_producer = model.ComponentIds_Get()[0]
    available = replace(
        unconstrained,
        producer_components=(selected_producer,),
    )
    assert LogAvailability_Get(available, model, builtin_catalog).available


def test_logging_view_has_one_cadence_surface() -> None:
    fields = LoggingStreamView.__dataclass_fields__
    assert "rate_text" not in fields
    assert {"cadence_kind", "cadence_text", "cadence_source"}.issubset(fields)


def test_task_finish_only_reaches_one_hundred_percent_on_success(
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(SettingsStore(tmp_path / "task-settings.ini"))
    try:
        window._last_task_progress = 370
        window._worker_outcome = (
            "result",
            BuildResult(BuildAction.BUILD, ("make",), 1, "failed"),
            "",
        )
        window._Task_Finish()
        window._progress_hide_timer.stop()
        assert window.progress_bar.value() == 370
        assert window.progress_bar.property("taskState") == "error"

        window._last_task_progress = 420
        window._worker_outcome = ("cancelled", None, "")
        window._Task_Finish()
        window._progress_hide_timer.stop()
        assert window.progress_bar.value() == 420
        assert window.progress_bar.property("taskState") == "cancelled"

        window._last_task_progress = 650
        window._worker_outcome = (
            "result",
            BuildResult(BuildAction.BUILD, ("make",), 0, "passed"),
            "",
        )
        window._Task_Finish()
        window._progress_hide_timer.stop()
        assert window.progress_bar.value() == 1000
        assert window.progress_bar.property("taskState") == "success"
    finally:
        window.close()
        qapp.processEvents()


def test_expected_compile_rejection_is_neutral_and_raw_error_is_detailed(
    tmp_path: Path,
    qapp,
) -> None:
    window = MainWindow(
        SettingsStore(tmp_path / "host-log-settings.ini"), language="zh_CN"
    )
    try:
        window.build_page.BuildLog_Set("")
        window.build_page.BuildDetailLog_Set("")
        window._BuildLine_Append(
            "FCCG_EXPECTED_REJECTION|capability_impact_unqualified"
        )
        window._BuildLine_Append(
            "FCCG_DETAIL|error: static assertion failed: impact is unavailable"
        )

        ordinary = window.build_page.build_log.toPlainText()
        detail = window.build_page.build_detail_log.toPlainText()
        assert "预期编译拒绝通过" in ordinary
        assert "当前IMU不支持冲击检测" in ordinary
        assert "static assertion failed" not in ordinary
        assert "static assertion failed" in detail
    finally:
        window.close()
        qapp.processEvents()
