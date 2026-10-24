"""Exhaustive bounded schedules and deterministic raw selection, no hardware."""
from itertools import permutations, product

import pytest

from services.installation_calibration_contract import InstallationContract_Load
from offline_proof import CancelBound_Evaluate, ModelResult, NativeSelector, SessionLeaseModel


def entrants():
    return InstallationContract_Load().Read()["session_lease"]["blocked_entrants"]


def test_fixed_five_hz_selection_never_looks_at_values_or_changes_native_rate():
    selected = []
    for values in ((0., 0., 0.), (999999., -999999., float("nan")), object()):
        selector = NativeSelector(40, 7, 250000, 210000)
        indices = [i for i in range(1200) if selector.Feed(i, i*5000, i*5000, values) == ModelResult.Selected]
        assert len(indices) == 30
        assert indices == list(range(7, 1200, 40))
        selected.append(indices)
    assert selected[0] == selected[1] == selected[2]


def test_unselected_native_gap_is_not_hidden_by_selected_stride():
    selector = NativeSelector(40, 0, 250000, 210000)
    assert selector.Feed(0, 0, 0, ()) == ModelResult.Selected
    assert selector.Feed(1, 5000, 5000, ()) == ModelResult.Skipped
    assert selector.Feed(3, 15000, 15000, ()) == ModelResult.Failed
    assert selector.Feed(40, 200000, 200000, ()) == ModelResult.Failed


def test_native_sequence_wrap_keeps_independent_stride_phase():
    selector = NativeSelector(40, 7, 250000, 210000)
    selected = [i for i in range(120) if selector.Feed((2**32-50+i) % 2**32, i*5000, i*5000, ()) == ModelResult.Selected]
    assert selected == [7, 47, 87]


def test_native_health_and_selected_cadence_have_separate_deadlines():
    selector = NativeSelector(40, 0, 20000, 210000)
    for i in range(40): assert selector.Feed(i, i*5000, i*5000, ()) != ModelResult.Failed
    assert selector.Poll(214999) == ModelResult.Failed  # selected output deadline, despite fresh native traffic
    selector = NativeSelector(40, 0, 20000, 210000)
    assert selector.Feed(0, 0, 0, ()) == ModelResult.Selected
    assert selector.Poll(20000) == ModelResult.Failed  # native deadline well before the next selected frame


def test_missing_first_native_frame_is_bounded_from_window_start():
    selector = NativeSelector(40, 7, 20000, 210000, start_us=1000000)
    assert selector.Poll(1019999) == ModelResult.Ok
    assert selector.Poll(1020000) == ModelResult.Failed


@pytest.mark.parametrize("first,second", list(product(entrants(), repeat=2)))
def test_every_entrant_pair_obeys_one_full_session_gate(first, second):
    gate = SessionLeaseModel(entrants())
    result, token = gate.Acquire(first)
    assert result == ModelResult.Ok
    assert gate.Acquire(second) == (ModelResult.Busy, None)
    assert gate.Cancel(token) == ModelResult.Ok
    assert not gate.CanPublish(token)
    assert gate.Acquire(second) == (ModelResult.Busy, None)
    assert gate.Acknowledge(token, producer=True, reader=True) == ModelResult.Ok
    assert gate.Release(token, remote_confirmed=True, local_release_confirmed=True) == ModelResult.Ok
    result, replacement = gate.Acquire(second)
    assert result == ModelResult.Ok and replacement.generation != token.generation
    assert not gate.CanPublish(token)


@pytest.mark.parametrize("order", list(permutations(("producer", "consumer", "reader"))))
def test_cancel_does_not_recycle_a_consumer_slot_before_all_acknowledgements(order):
    gate = SessionLeaseModel(entrants())
    _, token = gate.Acquire("INSTALL")
    assert gate.ConsumerAcquire(token) == ModelResult.Ok
    assert gate.Cancel(token) == ModelResult.Ok
    for i, participant in enumerate(order):
        assert gate.Acknowledge(token, **{participant: True}) == ModelResult.Ok
        expected = ModelResult.Ok if i == 2 else ModelResult.Unproven
        assert gate.Release(token, remote_confirmed=True, local_release_confirmed=True) == expected
    assert gate.state == "FREE"


@pytest.mark.parametrize("remote,local", ((False, False), (False, True), (True, False)))
def test_uncertain_cleanup_retains_the_lease(remote, local):
    gate = SessionLeaseModel(entrants())
    _, token = gate.Acquire("INSTALL"); gate.Cancel(token)
    gate.Acknowledge(token, producer=True, reader=True)
    assert gate.Release(token, remote_confirmed=remote, local_release_confirmed=local) == ModelResult.Unproven
    assert gate.Acquire("LOGFILE")[0] == ModelResult.Busy


def test_safety_recovery_revokes_publication_without_waiting_for_a_new_owner():
    gate = SessionLeaseModel(entrants())
    _, token = gate.Acquire("INSTALL")
    assert gate.CanPublish(token)
    gate.RevokeForRecovery()
    assert not gate.CanPublish(token) and gate.Acquire("START")[0] == ModelResult.Busy


def test_unknown_wcet_terms_cannot_be_zeroed_into_a_500_ms_pass():
    terms = dict.fromkeys(("host_interrupt", "rx_parse", "schedule_isr", "producer_stop", "consumer_ack",
                          "other_writers", "hal_dma_fault", "host_reader"))
    bound = CancelBound_Evaluate(115200, 4095, 1023, 192, terms)
    assert bound.result == ModelResult.Unproven and bound.total_us is None
    assert bound.known_wire_us == 460938 and len(bound.unknown_terms) == 8
    bounded = dict.fromkeys(terms, 0)  # explicitly synthetic complete-path counterexample
    bounded["host_interrupt"] = 5000000
    bound = CancelBound_Evaluate(115200, 4095, 1023, 192, bounded)
    assert bound.result == ModelResult.Failed and bound.total_us == 5460938
