"""Purpose classification, logging profile controls, and availability transitions."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractItemView
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LoggingProfile_AvailabilityTransitionApply,
    LoggingProfile_Reconcile,
    LogMetadataError,
    LogPolicyLevel,
    LogPurpose,
    ProjectProtocolLogMetadataPath_Get,
    ProtocolLogDefinitions_Get,
    ProtocolLogDefinitions_Load,
)
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    ProjectModel_Load,
    ProjectModel_Save,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import StandardCheckBox


def _States_Get(model) -> dict[str, bool]:
    return {stream.record: stream.enabled for stream in model.logging_streams}


def _Check_Get(window: MainWindow, record: str) -> StandardCheckBox:
    table = window.flight_configuration_page.logging_table
    for row in range(table.rowCount()):
        container = table.cellWidget(row, 0)
        check = container.findChild(StandardCheckBox) if container else None
        if check is not None and check.property("streamId") == record:
            return check
    raise AssertionError(f"Missing logging stream {record}")


def test_purpose_metadata_is_explicit_and_strict(
    tmp_path: Path, builtin_catalog
) -> None:
    model = ReferenceProject_Create("PurposeMetadata", catalog=builtin_catalog)
    metadata_path = ProjectProtocolLogMetadataPath_Get(model, builtin_catalog)
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    definitions = ProtocolLogDefinitions_Load(metadata_path)
    assert len(definitions) == 38
    assert {definition.purpose for definition in definitions} == {
        LogPurpose.FLIGHT, LogPurpose.TEST
    }
    assert {
        definition.name
        for definition in definitions
        if definition.purpose == LogPurpose.TEST
    } == {"KF6_DIAGNOSTIC", "KF6_FULL_P", "ESKF15_FULL_P_PART"}
    for definition in definitions:
        policy = data["fccg"]["records"][definition.record]
        assert policy["purpose"] == definition.purpose.value
        if definition.purpose == LogPurpose.TEST:
            assert definition.level == LogPolicyLevel.OPTIONAL
            assert not definition.default_stream.enabled
    overlay = json.loads(
        (Path(__file__).resolve().parents[1] /
         "tools/reference_overlays/sslog_fccg_metadata.json").read_text(
             encoding="utf-8"
         )
    )
    assert all(
        all(data["fccg"]["records"][record][key] == value
            for key, value in policy.items())
        for record, policy in overlay["fccg"]["records"].items()
    )

    record = definitions[0].record
    for invalid in (None, "unknown", 7):
        changed = deepcopy(data)
        if invalid is None:
            del changed["fccg"]["records"][record]["purpose"]
        else:
            changed["fccg"]["records"][record]["purpose"] = invalid
        path = tmp_path / "invalid-metadata.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(LogMetadataError, match="purpose"):
            ProtocolLogDefinitions_Load(path)


def test_fresh_kf6_and_pure_ins_defaults(builtin_catalog) -> None:
    model = ReferenceProject_Create("PurposeDefaults", catalog=builtin_catalog)
    definitions = ProtocolLogDefinitions_Get(model, builtin_catalog)
    states = _States_Get(model)
    for name in ("KF6_DIAGNOSTIC", "KF6_FULL_P"):
        record = f"FLIGHT_LOG_RECORD_{name}"
        definition = next(item for item in definitions if item.record == record)
        assert LogAvailability_Get(definition, model, builtin_catalog).available
        assert not states[record]

    model.strategies["estimator"] = None
    LoggingProfile_Reconcile(model, builtin_catalog)
    states = _States_Get(model)
    for name in ("KF6_DIAGNOSTIC", "KF6_FULL_P"):
        record = f"FLIGHT_LOG_RECORD_{name}"
        definition = next(item for item in definitions if item.record == record)
        assert not LogAvailability_Get(definition, model, builtin_catalog).available
        assert not states[record]


def test_availability_transition_preserves_choices_and_restores_defaults(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("PurposeTransition", catalog=builtin_catalog)
    gnss_native = "FLIGHT_LOG_RECORD_GNSS_NATIVE"
    gnss_measurement = "FLIGHT_LOG_RECORD_GNSS_MEASUREMENT"
    diagnostic = "FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC"
    model.logging_streams = [
        replace(stream, enabled=False) if stream.record == gnss_native
        else replace(stream, enabled=True) if stream.record == diagnostic
        else stream
        for stream in model.logging_streams
    ]
    previous = deepcopy(model)
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    assert not _States_Get(model)[gnss_native]
    assert _States_Get(model)[diagnostic]

    previous = deepcopy(model)
    model.strategies["estimator"] = None
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    states = _States_Get(model)
    assert not states[gnss_native]
    assert not states[gnss_measurement]
    assert not states[diagnostic]

    previous = deepcopy(model)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.kf6"
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    states = _States_Get(model)
    assert not states[gnss_native]
    assert states[gnss_measurement]
    assert not states[diagnostic]
    assert not states["FLIGHT_LOG_RECORD_KF6_FULL_P"]


def test_logging_protocol_reenable_restores_metadata_defaults(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("ProtocolTransition", catalog=builtin_catalog)
    diagnostic = "FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC"
    full_p = "FLIGHT_LOG_RECORD_KF6_FULL_P"
    model.logging_streams = [
        replace(stream, enabled=True)
        if stream.record in (diagnostic, full_p) else stream
        for stream in model.logging_streams
    ]
    selected = model.protocols["logging"]
    previous = deepcopy(model)
    model.protocols["logging"] = None
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    assert not any(_States_Get(model).values())
    previous = deepcopy(model)
    model.protocols["logging"] = selected
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    states = _States_Get(model)
    assert not states[diagnostic]
    assert not states[full_p]
    assert states["FLIGHT_LOG_RECORD_GNSS_MEASUREMENT"]


def test_three_logging_buttons_are_one_shot_and_save_only_stream_values(
    tmp_path: Path, qapp
) -> None:
    service = FccgService(Path(__file__).resolve().parents[1])
    window = MainWindow(
        SettingsStore(tmp_path / "purpose.ini"), service=service,
        language="en_US"
    )
    window.resize(1000, 700)
    window.show()
    window.navigation_list.setCurrentRow(1)
    qapp.processEvents()
    try:
        page = window.flight_configuration_page
        assert window.width() == 1000 and window.height() == 700
        assert all(
            button.mapTo(page.logging_group, QPoint(button.width(), 0)).x()
            <= page.logging_group.width()
            for button in (
                page.logging_select_all_button,
                page.logging_flight_only_button,
                page.logging_required_only_button,
                page.log_decoder_export_button,
            )
        )
        assert page.logging_table.horizontalScrollMode() == (
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        assert page.logging_table.verticalScrollMode() == (
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        assert page.logging_table.columnCount() == 7
        assert page.logging_table.horizontalHeaderItem(2).text() == "Purpose"
        assert [
            button.text() for button in (
                page.logging_select_all_button,
                page.logging_flight_only_button,
                page.logging_required_only_button,
            )
        ] == ["Enable All", "Flight Logs Only", "Required Only"]
        definitions = ProtocolLogDefinitions_Get(window._model, service.catalog)
        assert page.logging_table.item(
            next(index for index, definition in enumerate(definitions)
                 if definition.name == "KF6_DIAGNOSTIC"), 2
        ).text() == "Test"

        page.logging_select_all_button.click()
        qapp.processEvents()
        states = _States_Get(window._model)
        assert all(
            states[item.record] ==
            LogAvailability_Get(item, window._model, service.catalog).available
            for item in definitions
        )
        assert states["FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC"]
        assert states["FLIGHT_LOG_RECORD_KF6_FULL_P"]

        page.logging_flight_only_button.click()
        qapp.processEvents()
        states = _States_Get(window._model)
        assert all(
            states[item.record] == (LogAvailability_Get(item, window._model, service.catalog).available and (
                item.level == LogPolicyLevel.REQUIRED or
                item.purpose == LogPurpose.FLIGHT
            ))
            for item in definitions
        )
        for name in (
            "ESTIMATOR_STEP", "INERTIAL_INCREMENT", "GNSS_MEASUREMENT",
            "BARO_MEASUREMENT", "GNSS_NATIVE", "BARO_NATIVE",
            "IMU_CORRECTED", "GNSS_RECOVERY", "LANDING_DIAGNOSTIC"
        ):
            assert states[f"FLIGHT_LOG_RECORD_{name}"]

        page.logging_required_only_button.click()
        qapp.processEvents()
        states = _States_Get(window._model)
        assert all(
            states[item.record] == (item.level == LogPolicyLevel.REQUIRED and
                                   LogAvailability_Get(item, window._model, service.catalog).available)
            for item in definitions
        )
        page.logging_flight_only_button.click()
        qapp.processEvents()
        _Check_Get(window, "FLIGHT_LOG_RECORD_KF6_FULL_P").click()
        qapp.processEvents()
        assert _States_Get(window._model)["FLIGHT_LOG_RECORD_KF6_FULL_P"]

        project_file = tmp_path / "PurposeProfiles.ssproject"
        ProjectModel_Save(window._model, project_file, WorkspacePolicy(tmp_path))
        saved_data = json.loads(project_file.read_text(encoding="utf-8"))
        assert saved_data["format_version"] == PROJECT_FORMAT_VERSION
        assert "logging_profile" not in saved_data["logging"]
        saved = ProjectModel_Load(project_file)
        assert _States_Get(saved) == _States_Get(window._model)
    finally:
        window.close()
        qapp.processEvents()
