from dataclasses import replace

from protocol.air import AirAckMessage, AirStatusMessage
from protocol.common import AirCmdId, AirStatusId, AirAckResult
from services.state_model import FlightControllerState
from test_start_ack_state import make_controller, capability, preflight_status, add_pending, flight_state


def test_snapshot_before_capability_does_not_complete_unknown_handshake():
    c = make_controller()
    c._handle_preflight_status(preflight_status(capability_acked=True))
    assert not c.state.capability_acked
    assert not c.state.air_command_link_allowed()
    assert not c.worker.sent
    c._handle_capability(capability(255))
    assert c.pending_capability_ack is not None
    c._handle_preflight_status(preflight_status(capability_acked=True))
    assert c.state.capability_acked


def test_time_rollback_requires_two_samples_and_u32_wrap_is_not_reboot():
    c = make_controller()
    c._handle_capability(capability())
    c._handle_preflight_status(preflight_status(capability_acked=True))
    c.FlightTime_Observe(100000)
    c.FlightTime_Observe(100)
    assert c.state.capability_acked
    assert not c.state.air_command_link_allowed()
    c.FlightTime_Observe(100200)
    assert c.state.capability_acked
    assert c.state.air_command_link_allowed()
    c.FlightTime_Observe(100)
    c.FlightTime_Observe(300)
    assert not c.state.capability_acked
    assert c.state.capability is None
    generation = c.state.session_generation
    c.FlightTime_Observe(0xFFFFFF00)
    c.FlightTime_Observe(100)
    assert c.state.session_generation == generation


def test_mission_relative_clock_never_triggers_boot_relative_rollback():
    c = make_controller()
    c._handle_capability(capability())
    c._handle_preflight_status(preflight_status(capability_acked=True))
    c.FlightTime_Observe(100000)
    c._handle_flight_state(flight_state(100), None)
    c._handle_flight_state(flight_state(300), None)
    assert c.state.capability_acked
    assert c.state.mission_started
    assert not c.state.controller_restart_suspected


def test_framed_align_ack_is_transaction_acceptance_and_selftest_snapshot_wins():
    import struct
    from protocol.gsp_min import build_gsp_frame
    from protocol.common import GspType
    from protocol.receive_pipeline import ReceivePipeline
    from app import format_air_status_message
    c = make_controller()
    pipeline = ReceivePipeline()
    def receive(air):
        packet = build_gsp_frame(int(GspType.AIR_RX), bytes((186, 20, len(air))) + air)
        for event in pipeline.feed(packet):
            assert not event.air_error
            c._handle_air_message(event.air_message, event)
    receive(bytes((0x12, 250, 0, 1, 1, 15, 16, 0xD0, 7)))
    receive(struct.pack('<BBBBBI', 0x40, 251, c.pending_capability_ack.command_seq, 5, 0, 1000))
    c._handle_preflight_status(preflight_status(capability_acked=True, calibration_ready=True))
    c.send_align_start()
    pending = c._find_pending_air_cmd(int(AirCmdId.ALIGN_START))
    assert pending is not None and pending.air_frame[2] == int(AirCmdId.ALIGN_START)
    receive(struct.pack('<BBBBBI', 0x40, 252, pending.seq, pending.cmd_id, 0, 1200))
    assert not c.pending_air_cmds
    assert not c.state.alignment.ready
    assert not c.state.system_ready
    event = AirStatusMessage(253, int(AirStatusId.SELFTEST_COMPLETE), 1300, 0, 0)
    c._handle_status_message(event, None)
    assert not c.state.selftest_passed
    assert 'mission_capable=0' in format_air_status_message(event)
    c._handle_status_message(replace(event, arg0=1), None)
    assert c.state.selftest_passed
    c._handle_preflight_status(replace(preflight_status(capability_acked=True), selftest_passed=False))
    assert not c.state.selftest_passed
    assert not c.state.system_ready
    assert c.state.capability is not None


def test_boot_cancels_commands_and_rehandshakes_without_replay():
    c = make_controller()
    c._handle_capability(capability(250))
    c._handle_ack_message(AirAckMessage(1, c.pending_capability_ack.command_seq, 5, 0, 1000))
    c.state.system_ready = True
    c.state.start_unlocked = True
    add_pending(c, int(AirCmdId.START_MISSION), 19)
    c._handle_status_message(AirStatusMessage(0, int(AirStatusId.BOOT), 0, 0, 0), None)
    assert not c.state.capability_acked
    assert c.state.capability is None
    assert not c.state.system_ready
    assert not c.state.start_unlocked
    assert not c.pending_air_cmds
    c._handle_capability(capability(0))
    pending = c.pending_capability_ack
    assert pending is not None
    c._handle_ack_message(AirAckMessage(1, (pending.command_seq-1)&255, 5, 0, 1))
    assert not c.state.capability_acked
    c._handle_ack_message(AirAckMessage(2, pending.command_seq, 5, 0, 1))
    assert c.state.capability_acked
    generation = c.state.session_generation
    c._handle_status_message(AirStatusMessage(0, int(AirStatusId.BOOT), 0, 0, 0), None)
    assert c.state.session_generation == generation
    assert c.state.capability_acked


def test_disconnect_new_state_recovers_and_sequence_wrap_ignores_old_ack():
    c = make_controller()
    c._handle_capability(capability(254))
    c.state = FlightControllerState(session_generation=2, connected=True)
    c._clear_capability_ack('disconnect')
    c.air_seq = 255
    c._handle_preflight_status(preflight_status(capability_acked=True))
    assert not c.state.capability_acked
    c._handle_capability(capability(255))
    assert c.pending_capability_ack.command_seq == 255
    c._handle_capability(capability(0))
    assert c.pending_capability_ack.command_seq == 0
    # ACK from the superseded pending transaction does not authorize commands.
    c._handle_ack_message(AirAckMessage(1, 255, 5, int(AirAckResult.OK), 5))
    assert not c.state.capability_acked
    c._handle_preflight_status(preflight_status(capability_acked=True))
    assert c.state.capability_acked
