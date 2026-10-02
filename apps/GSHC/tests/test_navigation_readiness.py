from __future__ import annotations

import time
from dataclasses import replace

import pytest
from test_start_ack_state import capability, configure_ready, make_controller

from protocol.air import (
    TOKEN_NAV_SUBSCRIBE,
    AirAckMessage,
    AirNavigationCapabilityMessage,
    AirNavigationHealthMessage,
    AirNavigationPreparationMessage,
    AirStatusMessage,
    build_air_cmd,
    parse_air_frame,
)
from protocol.common import AirCmdId, AirStatusId, GspType
from protocol.gsp_min import build_gsp_frame
from protocol.receive_pipeline import ReceivePipeline, protocol_event_log_records
from services.navigation_state import (
    NavigationApplyResult,
    NavigationStartResult,
    NavigationState,
    PreparationSnapshot,
)


def archived_navigation_request(controller):
    """Simulate recorded extension negotiation, without Controller TX activation."""
    controller.state.navigation.Navigation_Request(42)
    controller.state.navigation.subscription_seq = 3


def navigation_ready(state, *, session=42, generation=1, seq=4, now=None):
    """A complete real protocol fixture, not a local READY override."""
    nav = state.navigation
    nav.Navigation_Request(session)
    assert nav.Navigation_Declare(1, session, generation, seq - 1) is NavigationApplyResult.APPLIED
    nav.algorithm_id = 1
    assert nav.Navigation_ApplyPreparation(PreparationSnapshot(
        session, generation, seq, 127, 127, 0, 0, 1, 7, 7,
        time.monotonic_ns() if now is None else now,
    )) is NavigationApplyResult.APPLIED


@pytest.mark.parametrize("raw,kind", [
    ("15223412070001021f", AirNavigationCapabilityMessage),
    ("1623341207007f0f11", AirNavigationPreparationMessage),
    ("172434120700090c00", AirNavigationHealthMessage),
])
def test_navigation_golden_and_gsp_log_roundtrip(raw, kind):
    wire = bytes.fromhex(raw)
    frame, message = parse_air_frame(wire)
    assert frame.raw == wire and len(wire) == 9
    assert isinstance(message, kind)
    assert message.session == 0x1234 and message.generation == 7
    packet = build_gsp_frame(int(GspType.AIR_RX), bytes((186, 20, 9)) + wire)
    event = ReceivePipeline().feed(packet, 123456789)[0]
    assert event.air_message == message
    record = next(item for item in protocol_event_log_records(event) if item.get("kind", "").startswith("NAV_"))
    assert record["session"] == 0x1234 and record["host_rx_monotonic_ns"] == 123456789


def test_navigation_subscribe_golden():
    wire = build_air_cmd(0x31, 0x0E, TOKEN_NAV_SUBSCRIBE | 0x1234, 1, 0)
    assert wire.hex() == "30310e3412564e0100"


@pytest.mark.parametrize("algorithm,allowed", [(0, True), (1, True), (2, True), (3, True), (4, False), (255, False)])
def test_declared_sf6_preserves_preparation_and_capability_start_gates(algorithm, allowed):
    controller = make_controller()
    configure_ready(controller)
    archived_navigation_request(controller)
    nav = controller.state.navigation
    controller.Navigation_HandleMessage(AirNavigationCapabilityMessage(
        5, nav.requested_session, 1, 1, algorithm, 31))
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(
        6, nav.session, 1, 127, 127, 0))
    assert controller.state.start_ready()  # M0 START admission stays authoritative.
    assert (nav.Navigation_StartCheck() is NavigationStartResult.ALLOWED) is allowed
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(
        7, nav.session, 1, 127, 15, 17))
    assert controller.state.start_ready()  # NAV failure stays visible, without a local START veto.
    controller.state.start_block_reason = 2  # Existing board M0 rejection still blocks START.
    assert not controller.state.start_ready()
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(
        8, nav.session, 1, 127, 127, 0))
    controller.state.capability = None
    assert not controller.state.start_ready()


@pytest.mark.parametrize("wire", [b"\x15" * 8, b"\x16" * 10, bytes.fromhex("172400000700090c00")])
def test_bad_navigation_length_or_zero_session_rejected(wire):
    with pytest.raises(ValueError):
        parse_air_frame(wire)


def test_ss0002_prepare_ack_and_alignment_ready_cannot_allow_start():
    controller = make_controller()
    configure_ready(controller)
    controller.state.navigation = NavigationState()
    assert controller.state.start_ready()  # Missing NAV schema is display-only.
    controller.state.system_ready = False
    archived_navigation_request(controller)
    nav = controller.state.navigation
    controller._handle_ack_message(AirAckMessage(4, nav.subscription_seq, 0x0E, 0, 200))
    assert nav.Navigation_StartCheck() is NavigationStartResult.UNSUPPORTED
    controller.Navigation_HandleMessage(AirNavigationCapabilityMessage(5, nav.requested_session, 1, 1, 1, 31))
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(6, nav.session, 1, 127, 15, 17))
    baseline = len(controller.worker.sent)
    controller.send_start()
    assert len(controller.worker.sent) == baseline
    assert not controller.state.mission_started
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(7, nav.session, 1, 127, 127, 0))
    assert not controller.state.start_ready()  # NAV cannot fabricate a board READY.
    controller.state.system_ready = True
    assert controller.state.start_ready()
    controller.send_start()
    assert len(controller.worker.sent) == baseline + 1


def test_release_does_not_offer_navigation_subscription():
    controller = make_controller()
    configure_ready(controller)
    assert not hasattr(controller, "Navigation_Subscribe")
    assert controller.state.start_ready()
    assert not controller.worker.sent

def test_stale_wrong_session_out_of_order_duplicate_and_generation():
    controller = make_controller()
    navigation_ready(controller.state, now=1_000_000_000)
    nav = controller.state.navigation
    old = nav.preparation
    assert nav.Navigation_StartCheck(3_000_000_001) is NavigationStartResult.STALE
    assert nav.Navigation_ApplyPreparation(replace(old, received_ns=3_000_000_000)) is NavigationApplyResult.DUPLICATE
    assert nav.Navigation_StartCheck(3_000_000_001) is NavigationStartResult.STALE
    assert nav.Navigation_ApplyPreparation(replace(old, session=43, snapshot=5)) is NavigationApplyResult.WRONG_SESSION
    assert nav.Navigation_ApplyPreparation(replace(old, snapshot=3)) is NavigationApplyResult.STALE
    assert nav.Navigation_ApplyPreparation(replace(old, generation=2, ready_mask=0)) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ApplyPreparation(replace(old, snapshot=5)) is NavigationApplyResult.STALE
    nav.Navigation_Request(43)
    assert nav.Navigation_Declare(1, 42, 2) is NavigationApplyResult.WRONG_SESSION
    assert nav.preparation is None and not nav.metrics


def test_health_fields_independent_expiry_unknown_selector_and_seq_wrap():
    controller = make_controller()
    navigation_ready(controller.state, now=1_000_000_000)
    nav = controller.state.navigation
    assert nav.Navigation_ApplyMetric(42, 1, 254, 0, 0x0253, 1_000_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ApplyMetric(42, 1, 255, 8, 10, 2_000_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ApplyMetric(42, 1, 0, 8, 20, 3_000_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ReadMetric(0, 0, 4_000_000_001) is None
    assert nav.Navigation_ReadMetric(0, 1, 4_000_000_001) == 20
    assert nav.Navigation_ApplyMetric(42, 1, 0, 8, 99, 4_000_000_000) is NavigationApplyResult.DUPLICATE
    assert nav.Navigation_ApplyMetric(42, 1, 1, 31 << 3, 99, 4_000_000_000) is NavigationApplyResult.UNSUPPORTED
    assert nav.Navigation_ApplyMetric(42, 2, 1, 0, 0x11, 4_000_000_000) is NavigationApplyResult.WRONG_SESSION


def test_start_retry_uses_board_admission_not_navigation_display_expiry():
    controller = make_controller()
    configure_ready(controller)
    navigation_ready(controller.state)
    controller.send_start()
    pending = controller._find_pending_air_cmd(int(AirCmdId.START_MISSION))
    assert pending is not None
    nav = controller.state.navigation
    nav.preparation = replace(nav.preparation, received_ns=time.monotonic_ns() - 3_000_000_000)
    count = len(controller.worker.sent)
    controller._transmit_pending_air_cmd(pending, is_retry=True)
    assert len(controller.worker.sent) == count + 1 and controller.pending_air_cmds
    controller.state.system_ready = False
    controller._transmit_pending_air_cmd(pending, is_retry=True)
    assert not controller.pending_air_cmds
    assert not controller._send_air_cmd(1, 0xA55A3CC3)


def test_required_mask_supports_explicit_pure_ins_without_inventing_gnss_origin():
    controller = make_controller()
    navigation_ready(controller.state)
    nav = controller.state.navigation
    nav.algorithm_id = 0
    assert nav.Navigation_ApplyPreparation(replace(nav.preparation, snapshot=5, required_mask=71, ready_mask=71)) is NavigationApplyResult.APPLIED
    assert nav.Navigation_StartCheck() is NavigationStartResult.ALLOWED
    assert not nav.preparation.ready_mask & 16


def test_local_reprepare_still_waits_for_real_board_alignment():
    controller = make_controller()
    configure_ready(controller)
    controller.send_align_start()
    assert not controller.state.start_ready()  # The real M0 command is pending.
    assert controller.state.navigation.preparation is None


@pytest.mark.parametrize("cause", ["disconnect", "boot"])
def test_connection_loss_or_boot_immediately_forgets_ready_and_old_nonce(cause):
    controller = make_controller()
    configure_ready(controller)
    navigation_ready(controller.state)  # Explicit archived-extension fixture.
    old = controller.state.navigation.preparation
    if cause == "disconnect":
        controller.on_connection_changed(False, "lost")
    else:
        controller._handle_status_message(AirStatusMessage(20, int(AirStatusId.BOOT), 0, 0, 0), None)
    assert not controller.state.start_ready()
    assert controller.state.navigation.preparation is None
    assert controller.state.navigation.Navigation_Declare(1, old.session, old.generation, 21) is NavigationApplyResult.WRONG_SESSION


def test_detail_selectors_and_ttl_cannot_refresh_primary_health():
    nav = NavigationState()
    nav.Navigation_Request(42)
    nav.Navigation_Declare(1, 42, 1)
    assert nav.Navigation_ApplyMetric(42, 1, 1, 0, 0x11, 1_000_000_000) is NavigationApplyResult.APPLIED
    for metric in range(4, 9):
        assert nav.Navigation_ApplyMetric(42, 1, 2, metric * 8 + 4, 10, 2_000_000_000) is NavigationApplyResult.APPLIED
    for metric in range(17):
        assert nav.Navigation_ApplyMetric(42, 1, 3, metric * 8 + 7, 100, 2_000_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ReadMetric(0, 0, 4_000_000_001) is None
    assert nav.Navigation_ReadMetric(7, 1, 4_000_000_001) == 100
    assert nav.Navigation_MetricAge(4, 4, 4_000_000_000) == 3000
    assert nav.Navigation_ReadMetric(7, 1, 12_000_000_001) is None
    assert nav.Navigation_ApplyMetric(42, 1, 4, 17 * 8 + 7, 0, 2_000_000_000) is NavigationApplyResult.UNSUPPORTED
    assert nav.Navigation_ApplyMetric(42, 1, 4, 5, 0, 2_000_000_000) is NavigationApplyResult.UNSUPPORTED


def test_sparse_detail_sequence_unwrap_uses_intervening_navigation_frames():
    nav = NavigationState()
    nav.Navigation_Request(42)
    nav.Navigation_Declare(1, 42, 1, 1)
    assert nav.Navigation_ApplyMetric(42, 1, 2, 7, 4, 0) is NavigationApplyResult.APPLIED
    for sequence in range(12, 303, 10):
        assert nav.Navigation_ApplyMetric(42, 1, sequence & 255, 1, 0x11, sequence * 1_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ApplyMetric(42, 1, 303 & 255, 7, 5, 303_000_000) is NavigationApplyResult.APPLIED
    assert nav.Navigation_ReadMetric(7, 0, 303_000_000) == 5
    assert nav.Navigation_ApplyMetric(42, 1, 302 & 255, 7, 4, 304_000_000) is NavigationApplyResult.STALE


@pytest.mark.parametrize("algorithm", [0, 1, 2, 3])
def test_optional_gnss_origin_does_not_block_start(algorithm):
    controller = make_controller()
    configure_ready(controller)
    archived_navigation_request(controller)
    nav = controller.state.navigation
    controller.Navigation_HandleMessage(AirNavigationCapabilityMessage(
        5, nav.requested_session, 1, 1, algorithm, 31))
    # Actual board contract: devices/calibration/attitude/baro/estimator required;
    # GNSS solution (8) and origin (16) remain absent and optional.
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(
        6, nav.session, 1, 0x67, 0x67, 0))
    assert controller.state.start_ready()
    # Explicit required GNSS keeps the same readiness and wire validation.
    controller.Navigation_HandleMessage(AirNavigationPreparationMessage(
        7, nav.session, 1, 0x7F, 0x67, 0))
    assert nav.Navigation_StartCheck() is NavigationStartResult.INCOMPLETE
    assert controller.state.start_ready()  # NAV details never override the M0 view.
    controller.state.alignment.ready = False  # Required GNSS is rejected by board Alignment/M0.
    assert not controller.state.start_ready()
