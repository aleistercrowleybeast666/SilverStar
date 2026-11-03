from types import SimpleNamespace

import pytest

from test_ss_tm import cap, event, packet, receive
from test_tm_receive_order import data
from test_start_ack_state import make_controller


@pytest.mark.parametrize("first_cap", [False, True])
def test_stage_events_on_either_side_of_cap_keep_preflight_link(first_cap):
    controller = make_controller()
    if first_cap:
        receive(controller, cap(0))
    for seq, code in enumerate((0x100, 0x100, 0x101), 1):
        identity = 1 if code == 0x100 else 2
        receive(controller, event(identity, seq, code=code, occurred=10))
    receive(controller, cap(4, timestamp=4_000_000))
    assert not controller.state.telemetry.passive
    assert controller.worker.sent
    assert not controller.state.mission_started


def test_telemetry_disconnect_preserves_position_but_clears_live_facts():
    controller = make_controller()
    controller.window = SimpleNamespace(bind_runtime_model=lambda *args, **kwargs: None)
    controller._state_generation = 1
    receive(controller, cap(0))
    from test_ss_tm import position
    receive(controller, position(1))
    before = controller.state.telemetry
    controller._replace_state(connected=False, connection_text='disconnected')
    assert before.passive is False
    assert controller.state.telemetry.passive
    assert controller.state.telemetry.boot_session is None
    assert controller.state.recovery.absolute.session == 123
    assert not controller.state.air_command_link_allowed()
    controller._replace_state(connected=True, connection_text='reconnecting')
    assert controller.state.telemetry.passive
    assert not controller.state.air_command_link_allowed()

@pytest.mark.parametrize("consumer", ["ground", "gshc"])
def test_same_wire_facts_govern_both_receivers(consumer, tmp_path):
    import ctypes
    import shutil
    import subprocess
    from pathlib import Path
    from services.telemetry_session import TelemetrySession
    from silverstar_telemetry.codec import Frame_Decode, TelemetryProtocolError

    if consumer == 'ground':
        gcc = shutil.which('gcc')
        if gcc is None:
            pytest.skip('Host GCC unavailable')
        plugins = Path(__file__).resolve().parents[2] / 'SCG/plugins/builtin'
        common = plugins / 'silverstar_core_0_1_0/payload/Common'
        ground = plugins / 'silverstar_core_ground_0_1_0/payload/Ground'
        library = tmp_path / 'receive-policy.dll'
        subprocess.run([gcc, '-std=c11', '-O2', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-pedantic', '-fanalyzer', '-I' + str(common / 'Inc'),
                        '-I' + str(ground / 'Core/Inc'), str(ground / 'Radio/Src/ground_radio_tm.c'),
                        str(common / 'Src/silverstar_assert.c'), '-o', str(library)], check=True)
        native = ctypes.CDLL(str(library))
        native.GroundRadioTm_Observe.argtypes = [ctypes.c_char_p, ctypes.c_uint8]
        native.GroundRadioTm_Observe.restype = None
        native.GroundRadioTm_PassiveGet.restype = ctypes.c_uint8
        def observe(raw):
            native.GroundRadioTm_Observe(raw, len(raw))
            return bool(native.GroundRadioTm_PassiveGet())
    else:
        owner = TelemetrySession()
        def observe(raw):
            try:
                frame = Frame_Decode(raw)
            except TelemetryProtocolError:
                return owner.passive
            owner.Frame_Observe(frame, 1)
            return owner.passive
    seq = 0
    for session, mission in enumerate(('START_ACK', 'FLIGHT_DATA', 'START_EVENT', 'LAUNCH_EVENT'), 100):
        ready = event(1, seq, session, code=0x100)
        assert observe(ready)
        assert not observe(cap(seq+1, session))
        from test_ss_tm import position
        bad = bytearray(position(seq+1, session+1000))
        bad[26] = 0x80
        assert not observe(bytes(bad))
        broken_health = bytearray(packet('HEALTH', seq+1, session+1000,
            battery_mv=12000, battery_age_ds=1, known_mask=1, fault_mask=0))
        broken_health[14] = 2
        assert not observe(bytes(broken_health))
        bad_data = bytearray(data(seq+1, session+1000))
        bad_data[32:36] = bytes.fromhex('0000c07f')
        assert not observe(bytes(bad_data))
        assert not observe(event(1, seq+2, session, code=0x100))
        assert not observe(event(2, seq+3, session, code=0x101))
        assert not observe(packet('ACK', seq+4, session, acked_sequence=2, command_id=1, result=1, time_ms=20))
        authority = {
            'START_ACK': packet('ACK', seq+5, session, acked_sequence=2, command_id=1, result=0, time_ms=20),
            'FLIGHT_DATA': data(seq+5, session, stamp=20),
            'START_EVENT': event(3, seq+5, session, code=3),
            'LAUNCH_EVENT': event(3, seq+5, session, code=4),
        }[mission]
        assert observe(authority)
        assert observe(cap(seq+6, session, timestamp=99_000_000))
        assert observe(event(4, seq+7, session, code=0x100))
        if session > 100:
            assert observe(cap(seq+8, session-1, timestamp=100_000_000))
        seq += 10

def test_worker_drains_before_reconnect_and_keeps_only_direction_and_replay_facts(tmp_path):
    from transport.protocol_worker import ProtocolWorker
    from test_receive_pipeline import air_rx_gsp
    from test_ss_tm import position
    from services.telemetry_session import TelemetryObserveResult

    controller = make_controller()
    controller.logger.session_active = False
    controller._connection_generation = controller._state_generation = 1
    controller.window = SimpleNamespace(bind_runtime_model=lambda *args, **kwargs: None)
    controller.link = SimpleNamespace(close=lambda: True)
    worker = ProtocolWorker(1, controller.logger, recovery_cache_path=tmp_path/'point.json')
    controller.protocol_worker = worker
    worker.start()
    worker.enqueue_chunk_with_timestamp(b''.join(air_rx_gsp(row) for row in (
        cap(0), position(1), data(2))), 1_000_000_000)
    # The GUI hasn't drained a single event. The ordered worker's last fact,
    # including the final position, still belongs to the old connection.
    controller.disconnect()
    assert controller.protocol_worker is None
    point = controller.state.recovery.Snapshot_Get(2_000_000_000, connected=True, current_session=123)
    assert point['age_s'] == 2 and not point['source_current']
    next_worker = ProtocolWorker(2, controller.logger, telemetry_reconnect=controller._telemetry_reconnect)
    frames = next_worker._pipeline.feed(b''.join(air_rx_gsp(row) for row in (
        cap(0), cap(3, timestamp=50_000_000), cap(1, session=300), cap(5))), 2_000_000_000)
    assert [x.telemetry_result for x in frames] == [
        TelemetryObserveResult.Duplicate, TelemetryObserveResult.Accepted,
        TelemetryObserveResult.Accepted, TelemetryObserveResult.Retired]
    assert [x.telemetry_snapshot.passive for x in frames] == [True, True, False, False]
    assert all(x.telemetry_snapshot.health is None for x in frames)


def test_historical_radio_frames_do_not_send_or_change_active_scales():
    from protocol.receive_pipeline import ReceivePipeline
    from transport.protocol_worker import ProtocolBatch
    from test_receive_pipeline import air_rx_gsp, capability_frame
    from test_tm_receive_order import flight_log
    controller = make_controller()
    controller._connection_generation = 4
    parser = ReceivePipeline()
    historic = bytearray(capability_frame())
    historic[4] = 0x87
    historic[6] = 32
    def receive_batch(raw):
        events = parser.feed(air_rx_gsp(bytes(raw)))
        controller.on_protocol_batch(ProtocolBatch(4, tuple(events)))
        return events[0]
    retained = receive_batch(historic)
    assert retained.air_message.calibration_mode_mask == 0x87
    assert not controller.worker.sent
    receive_batch(cap(1))
    sent = len(controller.worker.sent)
    receive_batch(historic)
    receive_batch(packet('CAPABILITY', 2, session=777, profile='H', flight_encoding=0, command_policy=2,
        calibration_mode_mask=7, sensor_summary_flags=15, accel_full_scale_g=32,
        gyro_full_scale_dps=2000, preflight_flags=1, advertised_monotonic_us=3000))
    assert controller.state.telemetry.boot_session == 123 and len(controller.worker.sent) == sent
    assert flight_log(receive_batch(data(3)))['accel_full_scale_g'] == 16
