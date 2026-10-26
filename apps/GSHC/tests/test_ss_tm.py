import pytest

from protocol.ss_tm import TelemetryCommand_Build
from silverstar_telemetry.codec import Frame_Encode, Frame_Decode, TelemetryProtocolError
from protocol.receive_pipeline import ReceivePipeline, protocol_event_log_records
from protocol.gsp_min import build_gsp_frame
from protocol.common import GspType
from services.telemetry_session import TelemetrySession, TelemetryObserveResult
from services.recovery_position import RecoveryPosition, RecoveryObserveResult, Recovery_Text
from test_start_ack_state import make_controller


def packet(name, sequence=0, session=123, profile='S', **values):
    return Frame_Encode(profile, name, sequence, session, values)


def position(sequence=0, session=123, age=1000, flags=5, latitude=0):
    return packet('POSITION', sequence, session, latitude_e7=latitude, longitude_e7=0,
        ellipsoid_height_mm=-2147483648, sample_age_ms=age, horizontal_accuracy_cm=65535,
        position_flags=flags, satellite_count=255)


def receive(controller, raw, timestamp=1_000_000_000):
    wire = build_gsp_frame(int(GspType.AIR_RX), bytes((186, 20, len(raw))) + raw)
    event, = ReceivePipeline().feed(wire, timestamp)
    assert not event.air_error
    controller._handle_air_message(event.air_message, event)
    return event


def cap(sequence=0, session=123, timestamp=1_000_000):
    return packet('CAPABILITY', sequence, session, flight_encoding=0, command_policy=1,
        calibration_mode_mask=7, sensor_summary_flags=15, accel_full_scale_g=16,
        gyro_full_scale_dps=2000, preflight_flags=1, advertised_monotonic_us=timestamp)


def event(event_id, sequence=0, session=123, code=3, occurred=2_000_000):
    return packet('EVENT', sequence, session, event_id=event_id, occurred_us=occurred,
        event_code=code, stage_id=0, instance_id=0, transaction_id=0, arg0=0, arg1=0)


def test_independent_position_health_and_lossless_logging():
    controller = make_controller()
    observed = receive(controller, position())
    snapshot = controller.state.recovery.Snapshot_Get(2_000_000_000)
    assert snapshot['latitude'] == snapshot['longitude'] == 0
    assert snapshot['age_s'] == 2
    assert 'WGS84' in Recovery_Text(snapshot)
    assert not controller.worker.sent
    records = protocol_event_log_records(observed)
    assert any(row.get('raw_hex') == position().hex() for row in records)
    receive(controller, packet('HEALTH', 1, battery_mv=0, battery_age_ds=10, known_mask=7, fault_mask=2))
    health = controller.state.telemetry.HealthSnapshot_Get(14_000_000_000)
    assert health['battery_mv'] == 0
    assert health['current_known_mask'] == 0
    assert health['stale']


def test_retained_age_wrap_invalid_new_point_and_disconnected_retention():
    recovery = RecoveryPosition()
    recovery.Absolute_Observe(Frame_Decode(position(65535)), 1_000_000_000, source='GNSS')
    recovery.Absolute_Observe(Frame_Decode(position(0, age=1000, flags=17)), 5_000_000_000, source='GNSS')
    assert recovery.Snapshot_Get(6_000_000_000)['age_s'] == 6
    assert recovery.Absolute_Observe(Frame_Decode(position(65535)), 7_000_000_000, source='GNSS') is RecoveryObserveResult.Older
    bad = packet('POSITION', 1, latitude_e7=-2147483648, longitude_e7=-2147483648,
        ellipsoid_height_mm=-2147483648, sample_age_ms=0xFFFFFFFF,
        horizontal_accuracy_cm=65535, position_flags=0, satellite_count=255)
    assert recovery.Absolute_Observe(Frame_Decode(bad), 8_000_000_000, source='GNSS') is RecoveryObserveResult.Invalid
    assert recovery.Snapshot_Get(9_000_000_000, connected=False)['age_s'] == 9


def test_real_event_dedup_start_segments_and_late_cap_no_uplink():
    controller = make_controller()
    receive(controller, cap(500))
    assert controller.worker.sent
    sent = len(controller.worker.sent)
    receive(controller, event(1, 501))
    receive(controller, event(1, 502))
    assert len(controller.state.telemetry.missions) == 1
    assert controller.state.telemetry.passive
    receive(controller, cap(499, timestamp=1_500_000))
    assert len(controller.worker.sent) == sent
    receive(controller, event(2, 503))
    assert len(controller.state.telemetry.missions) == 2
    assert controller.state.telemetry.last_stage_id is None
    assert not controller.state.air_command_link_allowed()


def test_boot_identity_cancels_and_rejects_retired_sessions():
    controller = make_controller()
    receive(controller, cap(1, session=300))
    assert controller.pending_capability_ack is not None
    receive(controller, position(session=2))  # random IDs have no ordering
    assert controller.pending_capability_ack is None
    assert not controller.pending_air_cmds
    receive(controller, cap(2, session=300, timestamp=3_000_000))
    assert controller.state.telemetry.boot_session == 2
    assert controller.state.telemetry.passive


def test_ack_16_bit_and_unknown_version_is_not_legacy():
    raw = TelemetryCommand_Build('S', 123, 65535, 5, 0, 0xEF, 0xBE)
    assert Frame_Decode(raw).values['param1'] == 0xBE
    controller = make_controller()
    receive(controller, packet('ACK', 8, acked_sequence=0xBEEF, command_id=1, result=0, time_ms=3000))
    assert controller.state.telemetry.passive
    assert not controller.state.telemetry.missions
    assert controller.state.telemetry.last_stage_id is None
    malformed = bytearray(raw); malformed[0] = 2
    with pytest.raises(TelemetryProtocolError): Frame_Decode(bytes(malformed))


def test_same_event_id_different_content_is_rejected():
    model = TelemetrySession()
    first = Frame_Decode(event(5))
    assert model.Frame_Observe(first, 1) is TelemetryObserveResult.Accepted
    assert model.Frame_Observe(Frame_Decode(event(5, sequence=1)), 2) is TelemetryObserveResult.Duplicate
    assert model.Frame_Observe(Frame_Decode(event(5, sequence=2, occurred=3_000_000)), 3) is TelemetryObserveResult.Conflict


def test_duplicate_health_cannot_renew_normal_or_battery_sample_age():
    model = TelemetrySession()
    raw = packet('HEALTH', 65535, battery_mv=12000, battery_age_ds=100, known_mask=7, fault_mask=0)
    frame = Frame_Decode(raw)
    assert model.Frame_Observe(frame, 1_000_000_000) is TelemetryObserveResult.Accepted
    assert model.Frame_Observe(frame, 10_000_000_000) is TelemetryObserveResult.Duplicate
    health = model.HealthSnapshot_Get(15_000_000_000)
    assert health['stale'] and health['current_known_mask'] == 0
    assert health['battery_age_s'] == 24
    wrapped = Frame_Decode(packet('HEALTH', 0, battery_mv=12000, battery_age_ds=240, known_mask=7, fault_mask=0))
    assert model.Frame_Observe(wrapped, 15_000_000_000) is TelemetryObserveResult.Accepted
