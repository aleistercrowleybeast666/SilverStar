from __future__ import annotations

from pathlib import Path

import pytest

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import (
    START_TIMESTAMP_US,
    AlignmentResult_Payload,
    AnalysisFlight_Build,
    Event_Payload,
    InitialState_Payload,
    StationaryFlight_Build,
    SyntheticSslogBuilder,
)


def test_overview_uses_real_calibration_alignment_and_deploy_fields(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_overview.BIN")
    )
    summary = FlightSummary_Build(dataset)
    assert summary.source_name == "Pure INS / KF_6"

    calibration = summary.calibration
    assert calibration.present
    assert calibration.mode == 2
    assert calibration.state == 4
    assert calibration.ready
    assert calibration.completed_face_mask == 0x3F
    assert calibration.completed_faces == 6
    assert calibration.required_faces == 6
    assert calibration.samples == 190
    assert calibration.reject_count == 2
    assert calibration.retry_count == 1
    assert calibration.accel_bias_mps2 == pytest.approx((0.11, -0.22, 0.33))
    assert calibration.accel_scale == pytest.approx((1.01, 0.99, 1.02))
    assert calibration.gyro_bias_radps == pytest.approx((0.001, -0.002, 0.003))
    assert calibration.gyro_scale == pytest.approx((1.001, 0.999, 1.002))

    alignment = summary.alignment
    assert alignment.present
    assert alignment.mode == 3
    assert alignment.state == 3
    assert alignment.ready
    assert alignment.q_nb == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert alignment.quaternion_record == "INITIAL_STATE"
    assert alignment.known_yaw_deg == pytest.approx(12.5)
    assert alignment.magnetic_declination_deg is None
    assert alignment.sample_count == 240
    assert {"imu", "known_yaw", "gnss", "barometer"} <= set(alignment.used_sources)
    assert not alignment.historical_mode

    deploy = summary.deploy
    assert deploy.timestamp_us == START_TIMESTAMP_US + 110_000
    assert deploy.altitude_source == "KF_6"
    assert deploy.altitude_m == pytest.approx(55.0)
    assert deploy.actual_reason_recorded
    assert deploy.actual_trigger_mask == 0x02
    assert deploy.enabled_trigger_mask == 0x07
    assert deploy.trigger_value == pytest.approx(-2.13, abs=1.0e-5)
    assert deploy.trigger_value_kind == "vertical_velocity"
    assert deploy.trigger_threshold == pytest.approx(-2.0)
    assert summary.maximum_altitude_m == pytest.approx(80.0)


def test_overview_absent_calibration_is_na_not_invented(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_no_calibration.BIN")
    )
    assert not FlightSummary_Build(dataset).calibration.present


def test_enabled_deploy_mask_is_not_reported_as_actual_reason(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_deploy_without_detail.BIN",
            include_deploy_detail=False,
        )
    )
    summary = FlightSummary_Build(dataset)
    assert summary.source_name == "Pure INS / KF_6"
    deploy = summary.deploy
    assert deploy.timestamp_us == START_TIMESTAMP_US + 110_000
    assert deploy.altitude_m == pytest.approx(55.0)
    assert deploy.enabled_trigger_mask == 0x07
    assert not deploy.actual_reason_recorded
    assert deploy.actual_trigger_mask == 0
    assert deploy.trigger_value is None
    assert deploy.trigger_threshold is None


def test_deploy_altitude_falls_back_to_recorded_pure_ins(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_deploy_pure_ins_fallback.BIN",
            include_kf6=False,
        )
    )
    summary = FlightSummary_Build(dataset)
    assert summary.source_name == "Pure INS"
    deploy = summary.deploy
    assert deploy.altitude_source == "Pure INS"
    assert deploy.altitude_m == pytest.approx(49.5)


def test_alignment_sources_are_not_invented_without_alignment_result(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_alignment_without_result.BIN",
            include_alignment_result=False,
        )
    )
    alignment = FlightSummary_Build(dataset).alignment
    assert alignment.present
    assert alignment.q_nb == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert alignment.used_sources == ()
    assert alignment.selected_mask is None
    assert alignment.ready_mask is None
    assert alignment.attitude_source is None


def test_latest_valid_alignment_is_history_and_initial_state_is_authoritative(
    tmp_path: Path,
) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        0x18,
        AlignmentResult_Payload(
            state=3,
            ready=1,
            q_nb=(1.0, 0.0, 0.0, 0.0),
        ),
        START_TIMESTAMP_US - 30,
    )
    builder.Record_Add(
        0x18,
        AlignmentResult_Payload(
            state=5,
            ready=0,
            q_nb=(0.0, 0.0, 1.0, 0.0),
        ),
        START_TIMESTAMP_US - 20,
    )
    builder.Record_Add(
        0x0D,
        InitialState_Payload(
            alignment_algorithm=3,
            q_nb=(0.0, 1.0, 0.0, 0.0),
        ),
        START_TIMESTAMP_US - 10,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_alignment_history.BIN")
    )

    alignment = FlightSummary_Build(dataset).alignment
    assert alignment.history_count == 2
    assert alignment.ready_history_count == 1
    assert alignment.result_timestamp_us == START_TIMESTAMP_US - 30
    assert alignment.initial_state_timestamp_us == START_TIMESTAMP_US - 10
    assert alignment.initial_state_authoritative
    assert alignment.quaternion_record == "INITIAL_STATE"
    assert alignment.q_nb == pytest.approx((0.0, 1.0, 0.0, 0.0))
    assert alignment.state == 3
    assert alignment.ready


@pytest.mark.parametrize(
    ("mode", "known_yaw", "declination"),
    (
        (0, 12.5, None),
        (1, None, 3.25),
        (2, None, None),
    ),
)
def test_historical_alignment_modes_remain_displayable(
    tmp_path: Path,
    mode: int,
    known_yaw: float | None,
    declination: float | None,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / f"SYNTHETIC_alignment_mode_{mode}.BIN",
            alignment_algorithm=mode,
        )
    )
    alignment = FlightSummary_Build(dataset).alignment
    assert alignment.present
    assert alignment.mode == mode
    assert alignment.historical_mode
    assert alignment.known_yaw_deg == known_yaw
    assert alignment.magnetic_declination_deg == declination
    assert alignment.q_nb == pytest.approx((1.0, 0.0, 0.0, 0.0))


def test_overview_labels_and_timeline_events_are_bilingual() -> None:
    zh = Translator("zh_CN")
    en = Translator("en_US")
    assert zh.Text_Get("calibration.mode.six_face") == "六面校准"
    assert en.Text_Get("calibration.mode.six_face") == "Six-face Calibration"
    assert zh.Text_Get("alignment.mode.gravity_known_yaw") == "重力 + 已知偏航角"
    assert en.Text_Get("alignment.mode.gravity_known_yaw") == "Gravity + Known Yaw"
    assert zh.Text_Get("event.MISSION_START") == "任务开始"
    assert en.Text_Get("event.MISSION_START") == "Mission Start"
    assert zh.Text_Get("event.PARACHUTE_DEPLOY") == "开伞"
    assert en.Text_Get("event.PARACHUTE_DEPLOY") == "Parachute Deploy"
