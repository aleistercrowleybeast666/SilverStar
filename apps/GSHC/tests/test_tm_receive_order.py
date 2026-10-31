"""Regressions through the actual parser, worker mailbox and controller."""
from dataclasses import replace

import pytest

from protocol.air import AirFlightStateMessage
from protocol.receive_pipeline import ReceivePipeline, protocol_event_log_records
from services.telemetry_session import TelemetrySession, TelemetryObserveResult
from services.recovery_position import RecoveryPosition, RecoveryCacheResult
from silverstar_telemetry.codec import Frame_Decode
from transport.protocol_worker import ProtocolWorker
from test_receive_pipeline import air_rx_gsp, flight_frame
from test_ss_tm import cap, event, packet, position, receive
from test_start_ack_state import make_controller, FakeLogger


def data(sequence, session=123, stamp=200):
    # Payload construction uses the unchanged legacy numeric body, not a second
    # implementation of any receive/session decision.
    body = flight_frame(0, stamp)[2:]
    return bytes((1, 0x10)) + sequence.to_bytes(2, 'little') + session.to_bytes(4, 'little') + body


def scaled_cap(sequence, session, scale):
    frame = Frame_Decode(cap(sequence, session))
    return packet('CAPABILITY', sequence, session,
                  **(frame.values | {'accel_full_scale_g': scale}))


def flight_log(event):
    return next(row for row in protocol_event_log_records(event) if row.get('kind') == 'FLIGHT_STATE')


def test_retired_cap_and_same_boot_old_cap_cannot_poison_logged_scale():
    pipeline = ReceivePipeline()
    events = pipeline.feed(b''.join(air_rx_gsp(raw) for raw in (
        scaled_cap(0, 101, 16), scaled_cap(10, 202, 32),
        scaled_cap(1, 101, 16), scaled_cap(9, 202, 16), data(11, 202))))
    record = flight_log(events[-1])
    assert record['accel_full_scale_g'] == 32
    assert record['accel_mps2'][0] == pytest.approx(100 / 32768 * 32 * 9.80665)
    assert not any(row.get('kind') == 'CAPABILITY' for row in protocol_event_log_records(events[2]))
    # A new boot without its own CAP has raw values, never a borrowed scale.
    unknown, = pipeline.feed(air_rx_gsp(data(0, 303)))
    record = flight_log(unknown)
    assert record['accel_raw'] == [100, -100, 2048]
    assert record['physical_conversion_valid'] is False
    assert record['accel_mps2'] is None


def test_global_sequence_sparse_types_half_circle_and_full_wrap():
    session = TelemetrySession()
    assert session.Frame_Observe(Frame_Decode(cap(0)), 0) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(event(1, 1)), 1) is TelemetryObserveResult.Accepted
    # Both sparse CAP/EVENT types cross half-circle while global traffic stays continuous.
    for sequence in range(2, 32769):
        assert session.Frame_Observe(Frame_Decode(data(sequence)), sequence) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(cap(32769)), 32769) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(event(2, 32770)), 32770) is TelemetryObserveResult.Accepted
    for sequence in range(32771, 65537):
        assert session.Frame_Observe(Frame_Decode(data(sequence & 65535)), sequence) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(cap(1)), 65537) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(cap(1)), 65538) is TelemetryObserveResult.Duplicate
    assert session.Frame_Observe(Frame_Decode(event(2, 2)), 65539) is TelemetryObserveResult.Duplicate
    assert len(session._received_sequences) <= 256


def test_bounded_reordering_retains_unique_events_but_not_old_snapshots():
    session = TelemetrySession()
    for raw in (cap(100), event(2, 102, occurred=4_000_000), data(103)):
        assert session.Frame_Observe(Frame_Decode(raw), 1) is TelemetryObserveResult.Accepted
    assert session.Frame_Observe(Frame_Decode(event(1, 101)), 2) is TelemetryObserveResult.Accepted
    assert session.current_mission_key == (4_000_000, 2)
    assert session.Frame_Observe(Frame_Decode(cap(99)), 3) is TelemetryObserveResult.Duplicate
    # Long disconnect with an unprovable half-space jump remains fail closed.
    assert session.Frame_Observe(Frame_Decode(data(40000)), 4) is TelemetryObserveResult.Duplicate


def test_mailbox_saturation_and_same_chunk_timestamp_do_not_reorder_start():
    pipeline = ReceivePipeline()
    frames = [data(index, stamp=index * 200) for index in range(258)] + [event(1, 258)]
    events = pipeline.feed(b''.join(air_rx_gsp(raw) for raw in frames), 1_000_000_000)
    worker = ProtocolWorker(1, FakeLogger(), ui_mailbox_capacity=256)
    worker._publish_events(events)
    drained = []
    while (batch := worker.take_batch(17)) is not None:
        drained.extend(batch.events)
    sequences = [row.tm_frame.sequence for row in drained]
    assert sequences == sorted(sequences)
    ordinals = [row.ingress_ordinal for row in drained]
    assert ordinals == sorted(ordinals)
    assert drained[-2].tm_frame.sequence == 257
    assert drained[-1].tm_frame.sequence == 258


def test_mailbox_keeps_last_preboundary_sample_before_following_mission_data():
    pipeline = ReceivePipeline()
    frames = [data(index, stamp=index * 200) for index in range(258)]
    frames += [event(1, 258), data(259, stamp=0), data(260, stamp=200)]
    worker = ProtocolWorker(1, FakeLogger(), ui_mailbox_capacity=256)
    worker._publish_events(pipeline.feed(b''.join(air_rx_gsp(raw) for raw in frames), 1))
    drained = []
    while (batch := worker.take_batch(17)) is not None:
        drained.extend(batch.events)
    sequences = [item.tm_frame.sequence for item in drained]
    assert sequences[-3:] == [257, 258, 260]


def test_late_cap_boot_clock_does_not_reopen_uplink_after_mission_relative_data():
    controller = make_controller()
    receive(controller, data(0, stamp=200))
    receive(controller, cap(1, timestamp=9_000_000))
    assert controller.state.telemetry.passive
    assert not controller.worker.sent


def test_late_first_start_preserves_early_track_and_repeated_start_is_idempotent():
    controller = make_controller()
    receive(controller, data(0, stamp=200))
    receive(controller, data(1, stamp=400))
    assert len(controller.state.horizontal_trajectory.Snapshot_Get()[0]) == 2
    receive(controller, event(1, 2))
    receive(controller, event(1, 3))
    assert len(controller.state.horizontal_trajectory.Snapshot_Get()[0]) == 2
    assert controller.state.mission_first_time_ms == 200
    receive(controller, event(2, 4, occurred=5_000_000))
    assert controller.state.horizontal_trajectory.Snapshot_Get()[0] == []


def test_late_start_does_not_regress_received_launch_fact():
    from services.state_model import MissionPhase
    controller = make_controller()
    receive(controller, data(0, stamp=200))
    receive(controller, event(2, 2, code=4, occurred=4_000_000))
    receive(controller, event(1, 1, occurred=2_000_000))
    assert controller.state.mission_presentation.phase is MissionPhase.IN_FLIGHT
    assert controller.state.mission_started
    assert len(controller.state.horizontal_trajectory.Snapshot_Get()[0]) == 1


def test_position_and_health_refresh_link_age_without_refreshing_sample_age():
    controller = make_controller()
    receive(controller, position(0, age=9000), 5_000_000_000)
    assert controller.state.handshake.last_air_rx_monotonic_ns == 5_000_000_000
    receive(controller, packet('HEALTH', 1, battery_mv=12000, battery_age_ds=100,
                              known_mask=1, fault_mask=0), 6_000_000_000)
    assert controller.state.handshake.last_air_rx_monotonic_ns == 6_000_000_000
    assert controller.state.recovery.Snapshot_Get(6_000_000_000)['age_s'] == 10
    receive(controller, position(2, age=9000, flags=17), 7_000_000_000)
    assert controller.state.handshake.last_air_rx_monotonic_ns == 7_000_000_000
    assert controller.state.recovery.Snapshot_Get(7_000_000_000)['age_s'] == 11


def test_controller_uses_same_qualified_conversion_as_log():
    controller = make_controller()
    receive(controller, scaled_cap(0, 101, 16))
    receive(controller, scaled_cap(0, 202, 32))
    receive(controller, scaled_cap(1, 101, 16))
    observed = receive(controller, data(1, 202))
    assert list(controller.state.sensor.accel_mps2) == flight_log(observed)['accel_mps2']


def test_recovery_cache_restarts_without_reusing_old_process_monotonic_time(tmp_path):
    original = RecoveryPosition()
    original.Absolute_Observe(Frame_Decode(position(9, age=9000)), 80_000_000_000, source='GNSS')
    path = tmp_path / 'last-wgs84.json'
    assert original.Cache_Save(path, now_ns=81_000_000_000, wall_ns=100_000_000_000) is RecoveryCacheResult.Saved
    restored = RecoveryPosition()
    assert restored.Cache_Load(path, now_ns=2_000_000_000, wall_ns=105_000_000_000) is RecoveryCacheResult.Loaded
    snapshot = restored.Snapshot_Get(3_000_000_000, connected=True, current_session=123)
    assert snapshot['age_s'] == 16
    assert not snapshot['source_current']
    assert snapshot['latitude'] == snapshot['longitude'] == 0
    assert snapshot['sample'].restored
    # Wall-clock rollback cannot manufacture a younger precise observation.
    restored.Cache_Load(path, now_ns=2_000_000_000, wall_ns=99_000_000_000)
    assert restored.Snapshot_Get(3_000_000_000)['age_s'] is None
    path.write_text('{"schema": 1, "latitude_e7": NaN}', encoding='utf-8')
    previous = restored.absolute
    assert restored.Cache_Load(path) is RecoveryCacheResult.Invalid
    assert restored.absolute == previous


def test_worker_persists_only_accepted_valid_positions(tmp_path):
    path = tmp_path / 'last-wgs84.json'
    pipeline = ReceivePipeline()
    worker = ProtocolWorker(1, FakeLogger(), recovery_cache_path=path)
    events = pipeline.feed(air_rx_gsp(position(10, latitude=1234)))
    worker._persist_events(events)
    first = path.read_bytes()
    events = pipeline.feed(air_rx_gsp(position(9, latitude=9999)))
    worker._persist_events(events)
    assert path.read_bytes() == first


def test_recovery_panel_has_summary_details_and_wgs84_needs_no_enu_confirmation():
    from PySide6.QtWidgets import QApplication
    from ui.recovery_panel import RecoveryPanel
    application = QApplication.instance() or QApplication([])
    controller = make_controller()
    receive(controller, position(0), 1_000_000_000)
    panel = RecoveryPanel()
    panel.Render(controller.state)
    assert 'WGS84' in panel.summary.text()
    assert not panel.confirm.isVisible()
    assert panel.copy.isEnabled() and panel.map.isEnabled()
    assert '健康信息：尚未采集' in panel.health_summary.text()
    assert not panel.details.isChecked()
    panel.details.click()
    assert panel.details.isChecked()
    panel.deleteLater()
