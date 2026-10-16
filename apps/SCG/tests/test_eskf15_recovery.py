"""Real C policy + dense-P kernel; explicit synthetic/experimental evidence only."""

from __future__ import annotations

import ctypes as c
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "apps/SCG").is_dir())
KERNEL = (
    ROOT
    / "apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
)
MODULE = KERNEL
COMMON = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common"
FIXTURE = Path(__file__).parent / "fixtures/eskf15_recovery.c"
U8, U32, U64, F = c.c_uint8, c.c_uint32, c.c_uint64, c.c_float
P = c.POINTER


class State(c.Structure):
    _fields_ = [
        ("position", F * 3),
        ("velocity", F * 3),
        ("quaternion", F * 4),
        ("gyro_bias", F * 3),
        ("accel_bias", F * 3),
        ("covariance", (F * 15) * 15),
        ("timestamp_us", U64),
        ("source", U32),
        ("generation", U32),
        ("initialized", U8),
    ]


class Workspace(c.Structure):
    _fields_ = [
        ("f", F * 225),
        ("transition", F * 225),
        ("row", F * 15),
        ("candidate_p", F * 225),
        ("candidate_x", F * 16),
        ("correction", F * 15),
        ("h", F * 30),
        ("gain", F * 30),
        ("innovation_covariance", F * 4),
    ]


class FilterConfig(c.Structure):
    _fields_ = [
        (name, F)
        for name in ("gravity", "gyro_noise", "accel_noise", "gyro_rw", "accel_rw")
    ] + [
        ("nis_soft", F * 2),
        ("nis_hard", F * 2),
        ("maximum_r_scale", F),
        ("nis_disabled_mask", U8),
    ]


class Config(c.Structure):
    _fields_ = [
        (name, U64)
        for name in (
            "loss_gap_us",
            "stable_span_us",
            "maximum_interval_us",
            "cooldown_us",
        )
    ] + [
        ("identity", U32),
        ("stable_count", U8),
        ("reject_count", U8),
        ("confirmation_count", U8),
        ("maximum_attempts", U8),
        ("scale", F * 15),
        ("variance_cap", F * 15),
    ]


class Receipt(c.Structure):
    _fields_ = [("receive_us", U64), ("sequence", U32), ("valid", U8)]


class Qualification(c.Structure):
    _fields_ = [
        ("last_physical_us", U64),
        ("stable_start_us", U64),
        ("last_qualified_us", U64),
        ("loss_token", U32),
        ("chain", U32),
        ("stable_count", U8),
        ("in_outage", U8),
    ]


class Receive(c.Structure):
    _fields_ = [
        ("source", Receipt * 4),
        ("group", Qualification * 4),
        ("epoch_start_us", U64),
        ("horizon_us", U64),
        ("native_us", U64),
        ("mission", U32),
        ("calibration", U32),
        ("configuration", U32),
        ("ordinal", U32),
        ("selected_source", U8),
        ("selected_valid", U8),
        ("initialized", U8),
        ("exhausted", U8),
    ]


class Packet(c.Structure):
    _fields_ = [
        ("receive_us", U64),
        ("native_us", U64),
        ("source", U32),
        ("sequence", U32),
        ("mission", U32),
        ("calibration", U32),
        ("physical_mask", U8),
        ("coherent_mask", U8),
        ("time_proven", U8),
    ]


class Evidence(c.Structure):
    _fields_ = [
        ("ordinal", U32),
        ("chain", U32),
        ("loss_tokens", U32 * 4),
        ("qualified", U8),
        ("reserved", U8 * 3),
    ]


class Group(c.Structure):
    _fields_ = [
        ("loss_token", U32),
        ("chain", U32),
        ("ordinal", U32),
        ("rejects", U8),
        ("confirmations", U8),
    ]


class Policy(c.Structure):
    _fields_ = (
        [("group", Group * 4), ("last_scale_receive_us", U64)]
        + [
            (name, U32)
            for name in (
                "mission",
                "calibration",
                "configuration",
                "pending_ordinal",
                "pending_chain",
                "pending_loss",
                "last_scale_ordinal",
            )
        ]
        + [
            (name, U8)
            for name in (
                "pending_source",
                "pending_group",
                "pending_valid",
                "active_mask",
                "attempts",
                "limited",
                "initialized",
            )
        ]
    )


class Measurement(c.Structure):
    _fields_ = [
        ("group", U8),
        ("physically_valid", U8),
        ("observation", F * 2),
        ("variance", F * 2),
        ("lever_arm", F * 3),
        ("angular_rate", F * 3),
    ]


class Event(c.Structure):
    _fields_ = [
        ("receive_us", U64),
        ("source", U32),
        ("sequence", U32),
        ("mission", U32),
        ("calibration", U32),
        ("measurement", Measurement),
        ("evidence", Evidence),
    ]


class Transaction(c.Structure):
    _fields_ = [("state", State), ("policy", Policy)]


class Outcome(c.Structure):
    _fields_ = [
        ("nis", F),
        ("r_scale", F),
        ("innovation", F * 2),
        ("variance", F * 2),
        ("gain_norm", F),
        ("dimension", U8),
        ("result", c.c_int),
    ]


class Output(c.Structure):
    _fields_ = [("filter", Outcome), ("action", c.c_int)]


TYPES = (
    State,
    Workspace,
    FilterConfig,
    Config,
    Receipt,
    Qualification,
    Receive,
    Packet,
    Evidence,
    Group,
    Policy,
    Event,
    Transaction,
    Output,
    Measurement,
)
NAMES = (
    "complete",
    "duplicate",
    "discontinuity",
    "ineligible",
    "exhausted",
    "invalid",
    "numeric",
    "mismatch",
    "none",
    "pending",
    "scaled",
    "limited",
    "ok",
    "soft",
    "nis",
    "filter_invalid",
    "filter_numeric",
    "filter_mismatch",
    "measurement_invalid",
)


def clone(value):
    return type(value).from_buffer_copy(bytes(value))


def dense(seed=0):
    vector = [(-1 if (i + seed) % 2 else 1) * (i + 1) / 64 for i in range(15)]
    return ((F * 15) * 15)(
        *[
            (F * 15)(
                *[
                    vector[i] * vector[j] + (1 + i / 8 if i == j else 0)
                    for j in range(15)
                ]
            )
            for i in range(15)
        ]
    )


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def library(request, tmp_path_factory):
    gcc = shutil.which("gcc")
    assert gcc, "Real Host GCC required"
    directory = tmp_path_factory.mktemp("recovery" + request.param)
    output = directory / "recovery.dll"
    sources = [
        MODULE / "Src/navigation_eskf_recovery.c",
        KERNEL / "Src/navigation_eskf.c",
        COMMON / "Src/silverstar_assert.c",
        FIXTURE,
    ]
    command = [
        gcc,
        "-std=c11",
        request.param,
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-fno-fast-math",
        "-ffp-contract=off",
        "-shared",
        "-I" + str(MODULE / "Inc"),
        "-I" + str(KERNEL / "Inc"),
        "-I" + str(COMMON / "Inc"),
        *map(str, sources),
        "-lm",
        "-o",
        str(output),
    ]
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=90, check=False
    )
    metadata = {
        "command": command,
        "exit_code": done.returncode,
        "stdout": done.stdout,
        "stderr": done.stderr,
        "compiler": subprocess.check_output([gcc, "--version"], text=True),
        "source_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                *sources,
                MODULE / "Inc/navigation_eskf_recovery.h",
                KERNEL / "Inc/navigation_eskf.h",
            ]
        },
    }
    if output.exists():
        metadata["library_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (directory / "compile.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lib = c.CDLL(str(output))
    lib.Test_Size.argtypes = [U32]
    lib.Test_Size.restype = c.c_size_t
    assert [lib.Test_Size(i) for i in range(len(TYPES))] == [c.sizeof(t) for t in TYPES]
    lib.Test_Enum.argtypes = [U32]
    lib.Test_Enum.restype = c.c_int
    lib.values = dict(
        zip(NAMES, [lib.Test_Enum(i) for i in range(len(NAMES))], strict=True)
    )
    signatures = {
        "Test_Prepare": [
            P(State),
            P(Workspace),
            P(FilterConfig),
            P(Config),
            P(Receive),
            P(Policy),
            P(F * 15),
        ],
        "NavigationEskfRecovery_ConfigValidate": [P(Config)],
        "NavigationEskfRecovery_Reset": [
            P(Receive),
            P(Policy),
            P(Config),
            U32,
            U32,
            U64,
        ],
        "NavigationEskfRecovery_SourceSelect": [P(Receive), U32],
        "NavigationEskfRecovery_Tick": [P(Receive), P(Config), U64],
        "NavigationEskfRecovery_Receive": [
            P(Receive),
            P(Config),
            P(Packet),
            P(Evidence),
        ],
        "NavigationEskfRecovery_UpdateCandidate": [
            P(State),
            P(Policy),
            P(Workspace),
            P(Transaction),
            P(FilterConfig),
            P(Config),
            P(Event),
            P(Output),
        ],
        "NavigationEskf_Update": [
            P(State),
            P(Workspace),
            P(FilterConfig),
            P(Measurement),
            P(Outcome),
        ],
    }
    signatures["NavigationEskfRecovery_UpdateCandidateRevision2"] = signatures[
        "NavigationEskfRecovery_UpdateCandidate"
    ]
    signatures["NavigationEskf_UpdateRevision2"] = signatures["NavigationEskf_Update"]
    for name, signature in signatures.items():
        getattr(lib, name).argtypes = signature
        getattr(lib, name).restype = c.c_int
    return lib


class Rig:
    def __init__(self, lib, seed=0):
        self.lib = lib
        self.state, self.work, self.filter, self.config = (
            State(),
            Workspace(),
            FilterConfig(),
            Config(),
        )
        self.receive, self.policy, self.transaction, self.output = (
            Receive(),
            Policy(),
            Transaction(),
            Output(),
        )
        self.initial = dense(seed)
        assert (
            lib.Test_Prepare(
                self.state,
                self.work,
                self.filter,
                self.config,
                self.receive,
                self.policy,
                self.initial,
            )
            == lib.values["complete"]
        )

    def packet(self, sequence, time, source=0, **changes):
        packet = Packet(time, time, source, sequence, 7, 11, 15, 15, 1)
        for key, value in changes.items():
            setattr(packet, key, value)
        evidence = (Evidence * 4)()
        original = bytes(packet), bytes(self.config)
        result = self.lib.NavigationEskfRecovery_Receive(
            self.receive, self.config, packet, evidence
        )
        assert original == (bytes(packet), bytes(self.config))
        return result, evidence

    def update(self, event):
        original = (
            bytes(event),
            bytes(self.config),
            bytes(self.filter),
            bytes(self.receive),
        )
        before = bytes(self.state), bytes(self.policy)
        result = self.lib.NavigationEskfRecovery_UpdateCandidate(
            self.state,
            self.policy,
            self.work,
            self.transaction,
            self.filter,
            self.config,
            event,
            self.output,
        )
        assert original == (
            bytes(event),
            bytes(self.config),
            bytes(self.filter),
            bytes(self.receive),
        )
        if result != self.lib.values["complete"]:
            assert before == (bytes(self.state), bytes(self.policy))
        return result


def test_independent_native_epoch_does_not_share_mcu_origin(library):
    """Known iTOW remains a different axis from the admitted MCU receipt time."""
    rig = Rig(library)
    native_offset = 300_000_000_000
    assert (
        rig.packet(1, 1_000_000, native_us=native_offset + 1_000_000)[0]
        == library.values["complete"]
    )
    for sequence, now in [(2, 3_000_000), (3, 3_200_000), (4, 3_400_000)]:
        result, evidence = rig.packet(sequence, now, native_us=native_offset + now)
        assert result == library.values["complete"]
    assert [item.qualified for item in evidence] == [1] * 4
    # Same native epoch cannot qualify the next distinct MCU receipt.
    result, evidence = rig.packet(5, 3_600_000, native_us=native_offset + 3_400_000)
    assert result == library.values["complete"]
    assert not any(item.qualified for item in evidence)


def event(ordinal, group=0, source=0, value=1000.0, loss=(1, 1, 1, 1), qualified=True):
    item = Event()
    item.receive_us = ordinal * 1_000_000
    item.source, item.sequence, item.mission, item.calibration = source, ordinal, 7, 11
    item.measurement.group, item.measurement.physically_valid = group, 1
    item.measurement.observation[:] = [value, -value]
    item.measurement.variance[:] = [1.0, 1.0]
    item.evidence.ordinal, item.evidence.chain, item.evidence.qualified = (
        ordinal,
        1,
        qualified,
    )
    item.evidence.loss_tokens[:] = loss
    return item


def arm(rig):
    for ordinal in (1, 2):
        assert rig.update(event(ordinal)) == rig.lib.values["complete"]
        assert rig.output.filter.result == rig.lib.values["nis"]
    assert rig.policy.pending_valid and rig.policy.attempts == 0


@pytest.mark.parametrize("group", [2, 3])
@pytest.mark.parametrize("seed", range(8))
def test_revision2_ordinary_transaction_keeps_stable_covariance_reset(
    library, group, seed
):
    rig = Rig(library, seed)
    rig.filter.nis_disabled_mask = 1
    item = event(1, group=group, value=3.0)
    item.evidence = Evidence()
    item.measurement.lever_arm[:] = [0.8, -0.3, 0.2]
    item.measurement.angular_rate[:] = [0.4, 0.5, 0.7]
    # omega cross lever = (0.31, 0.48, -0.52). Keep the actual correction
    # inside the kernel's attitude/bias trust region while exercising reset.
    item.measurement.observation[:] = [0.36, 0.43] if group == 2 else [-0.47, 0.0]
    expected, legacy = clone(rig.state), clone(rig.state)
    expected_work, legacy_work = Workspace(), Workspace()
    expected_out, legacy_out = Outcome(), Outcome()
    assert (
        library.NavigationEskf_UpdateRevision2(
            expected, expected_work, rig.filter, item.measurement, expected_out
        )
        == library.values["ok"]
    )
    assert (
        library.NavigationEskf_Update(
            legacy, legacy_work, rig.filter, item.measurement, legacy_out
        )
        == library.values["ok"]
    )
    # Counterfactual proves that substituting the legacy kernel is detectable.
    assert bytes(legacy) != bytes(expected)
    policy_before = bytes(rig.policy)
    assert (
        library.NavigationEskfRecovery_UpdateCandidateRevision2(
            rig.state,
            rig.policy,
            rig.work,
            rig.transaction,
            rig.filter,
            rig.config,
            item,
            rig.output,
        )
        == library.values["complete"]
    )
    assert bytes(rig.state) == bytes(expected)
    assert bytes(rig.output.filter) == bytes(expected_out)
    assert bytes(rig.policy) == policy_before
    assert rig.output.action == library.values["none"]


def test_revision2_invalid_angular_rate_preserves_original_error_before_optional_scale(
    library,
):
    rig = Rig(library)
    arm(rig)
    item = event(3)
    item.measurement.angular_rate[0] = math.nan
    rig.state.covariance[0][0] = math.nan
    before = bytes(rig.state), bytes(rig.policy)
    result = library.NavigationEskfRecovery_UpdateCandidateRevision2(
        rig.state,
        rig.policy,
        rig.work,
        rig.transaction,
        rig.filter,
        rig.config,
        item,
        rig.output,
    )
    assert result == library.values["measurement_invalid"]
    assert rig.output.filter.result == library.values["filter_invalid"]
    assert rig.output.action == library.values["none"]
    assert before == (bytes(rig.state), bytes(rig.policy))


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", 0),
        ("loss_gap_us", 250000),
        ("maximum_interval_us", 0),
        ("stable_span_us", 0),
        ("cooldown_us", 0),
        ("stable_count", 1),
        ("reject_count", 0),
        ("confirmation_count", 0),
        ("maximum_attempts", 0),
    ],
)
def test_configuration_requires_explicit_valid_values(library, field, value):
    rig = Rig(library)
    setattr(rig.config, field, value)
    assert (
        library.NavigationEskfRecovery_ConfigValidate(rig.config)
        == library.values["invalid"]
    )


@pytest.mark.parametrize("value", [0, 1, 2.1, math.nan, math.inf, -math.inf, 1.5])
def test_nonuniform_invalid_scale_rejected(library, value):
    rig = Rig(library)
    rig.config.scale[7] = value
    assert (
        library.NavigationEskfRecovery_ConfigValidate(rig.config)
        == library.values["invalid"]
    )


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_invalid_caps_rejected(library, value):
    rig = Rig(library)
    rig.config.variance_cap[14] = value
    assert (
        library.NavigationEskfRecovery_ConfigValidate(rig.config)
        == library.values["invalid"]
    )


def test_four_source_bounce_does_not_reset_watermarks(library):
    rig = Rig(library)
    for source in range(4):
        assert (
            rig.packet(5, 1_000_000 + source, source)[0] == library.values["complete"]
        )
    before = bytes(rig.receive)
    assert rig.packet(5, 2_000_000, 0)[0] == library.values["duplicate"]
    assert bytes(rig.receive) == before
    assert rig.packet(6, 2_000_000, 0)[0] == library.values["complete"]
    assert rig.receive.ordinal == 5


def test_wrap_half_range_order_and_bad_proof_consumption(library):
    rig = Rig(library)
    assert rig.packet(0xFFFFFFFF, 1_000_000)[0] == library.values["complete"]
    assert rig.packet(0, 1_100_000)[0] == library.values["complete"]
    for sequence, time in [(0x80000000, 1_200_000), (1, 1_000_000)]:
        before = bytes(rig.receive)
        assert rig.packet(sequence, time)[0] == library.values["discontinuity"]
        assert bytes(rig.receive) == before
    assert rig.packet(1, 1_200_000, time_proven=0)[0] == library.values["complete"]
    assert rig.packet(1, 1_300_000)[0] == library.values["duplicate"]


@pytest.mark.parametrize(
    "changes", [{"mission": 8}, {"calibration": 12}, {"source": 4}, {"receive_us": 0}]
)
def test_bad_receipt_identity_is_transactional(library, changes):
    rig = Rig(library)
    before = bytes(rig.receive)
    assert rig.packet(1, 1_000_000, **changes)[0] == library.values["invalid"]
    assert bytes(rig.receive) == before


@pytest.mark.parametrize("seconds", [1, 5, 30, 120])
def test_outage_then_continuous_count_and_span(library, seconds):
    rig = Rig(library)
    _, evidence = rig.packet(1, 1_000_000)
    assert not any(e.qualified for e in evidence)
    now = 1_000_000 + seconds * 1_000_000
    assert (
        library.NavigationEskfRecovery_Tick(rig.receive, rig.config, now)
        == library.values["complete"]
    )
    for sequence, offset in [(2, 0), (3, 200000), (4, 400000)]:
        result, evidence = rig.packet(sequence, now + offset)
        assert result == library.values["complete"]
        assert [e.qualified for e in evidence] == [int(offset == 400000)] * 4
        assert [list(e.loss_tokens) for e in evidence] == [[1] * 4] * 4


@pytest.mark.parametrize(
    "changes",
    [{"physical_mask": 0}, {"coherent_mask": 0}, {"time_proven": 0}, {"native_us": 0}],
)
def test_unknown_or_bad_evidence_breaks_qualification(library, changes):
    rig = Rig(library)
    rig.packet(1, 1_000_000)
    rig.packet(2, 3_000_000)
    rig.packet(3, 3_200_000)
    _, evidence = rig.packet(4, 3_400_000, **changes)
    assert not any(e.qualified for e in evidence)
    assert all(g.stable_count == 0 for g in rig.receive.group)


def test_stability_needs_span_and_no_interval_gap(library):
    rig = Rig(library)
    rig.packet(1, 1_000_000)
    for sequence, time in [(2, 3_000_000), (3, 3_000_001), (4, 3_000_002)]:
        _, evidence = rig.packet(sequence, time)
    assert not any(e.qualified for e in evidence)
    _, evidence = rig.packet(5, 3_400_000)
    assert not any(e.qualified for e in evidence)
    assert all(g.stable_count == 1 for g in rig.receive.group)


def test_receive_before_tick_horizon_consumed_without_rewind(library):
    rig = Rig(library)
    rig.packet(1, 1_000_000)
    library.NavigationEskfRecovery_Tick(rig.receive, rig.config, 3_000_000)
    _, old = rig.packet(2, 2_000_000)
    assert not any(e.qualified for e in old)
    assert rig.receive.horizon_us == 3_000_000
    assert rig.packet(2, 3_100_000)[0] == library.values["duplicate"]


@pytest.mark.parametrize("counter", ["ordinal", "chain", "loss"])
def test_counter_exhaustion_does_not_wrap(library, counter):
    rig = Rig(library)
    rig.packet(1, 1_000_000)
    if counter == "ordinal":
        rig.receive.ordinal = 0xFFFFFFFF
        result = rig.packet(2, 1_100_000)[0]
        assert rig.receive.ordinal == 0xFFFFFFFF
    elif counter == "chain":
        rig.receive.group[0].chain = 0xFFFFFFFF
        result = library.NavigationEskfRecovery_SourceSelect(rig.receive, 1)
        assert rig.receive.group[0].chain == 0xFFFFFFFF
    else:
        rig.receive.group[0].loss_token = 0xFFFFFFFF
        result = library.NavigationEskfRecovery_Tick(rig.receive, rig.config, 3_000_000)
        assert rig.receive.group[0].loss_token == 0xFFFFFFFF
    assert result == library.values["exhausted"]


def test_nis_without_physical_loss_never_arms(library):
    rig = Rig(library)
    for i in range(1, 12):
        assert rig.update(event(i, loss=(0, 0, 0, 0))) == library.values["complete"]
    assert not rig.policy.pending_valid and rig.policy.attempts == 0
    assert bytes(rig.state.covariance) == bytes(rig.initial)


def test_four_groups_same_receipt_cannot_trigger_pending_scale(library):
    rig = Rig(library)
    for ordinal in (1, 2):
        for group in range(4):
            rig.update(event(ordinal, group))
    assert rig.policy.pending_valid and rig.policy.attempts == 0
    for group in range(4):
        rig.update(event(3, group))
    assert rig.policy.attempts == 1


@pytest.mark.parametrize("seed", [0, 1, 7])
def test_pending_scale_preserves_all_225_terms_on_rejected_update(library, seed):
    rig = Rig(library, seed)
    before = clone(rig.state)
    arm(rig)
    assert rig.update(event(3)) == library.values["complete"]
    assert rig.output.action == library.values["scaled"]
    assert rig.output.filter.result == library.values["nis"]
    for i in range(15):
        for j in range(15):
            assert rig.state.covariance[i][j] == before.covariance[i][j] * 4
            assert rig.state.covariance[i][j] != 0
    c.memmove(
        c.addressof(before.covariance),
        c.addressof(rig.state.covariance),
        c.sizeof(before.covariance),
    )
    assert bytes(before) == bytes(rig.state)


def test_global_budget_survives_bounce_and_loss_refresh(library):
    rig = Rig(library)
    for ordinal in range(1, 7):
        rig.update(event(ordinal))
    assert rig.policy.attempts == 2 and rig.policy.limited
    covariance = bytes(rig.state.covariance)
    for ordinal in range(7, 15):
        item = event(ordinal, source=ordinal % 4, loss=(ordinal,) * 4)
        item.evidence.chain = ordinal
        rig.update(item)
    assert rig.policy.attempts == 2 and bytes(rig.state.covariance) == covariance


def test_cap_is_limited_and_still_runs_normal_update(library):
    rig = Rig(library)
    rig.config.variance_cap[:] = [1.0] * 15
    arm(rig)
    before = bytes(rig.state)
    assert rig.update(event(3)) == library.values["complete"]
    assert (
        rig.output.action == library.values["limited"]
        and rig.output.filter.result == library.values["nis"]
    )
    assert (
        rig.policy.attempts == 1 and rig.policy.limited and bytes(rig.state) == before
    )


@pytest.mark.parametrize(
    "fault",
    [
        "scale_nan",
        "scale_asymmetry",
        "update_invalid",
        "model_mismatch",
        "update_numeric",
    ],
)
def test_combined_failures_preserve_authority_pair(library, fault):
    rig = Rig(library)
    arm(rig)
    item = event(3)
    if fault == "scale_nan":
        rig.state.covariance[14][14] = math.nan
        expected = "numeric"
    elif fault == "scale_asymmetry":
        rig.state.covariance[0][14] += 0.001
        expected = "numeric"
    elif fault == "update_invalid":
        item.measurement.variance[0] = -1
        expected = "measurement_invalid"
    elif fault == "model_mismatch":
        rig.filter.nis_disabled_mask = 3
        expected = "mismatch"
    else:
        rig.state.quaternion[:] = [0, 0, 0, 0]
        item.measurement.observation[:] = [0, 0]
        expected = "numeric"
    assert rig.update(item) == library.values[expected]
    assert rig.output.action == library.values["none"]
    if fault == "model_mismatch":
        assert rig.output.filter.result == library.values["filter_mismatch"]


def test_full_loss_snapshot_prevents_early_budget_reset(library):
    rig = Rig(library)
    rig.policy.attempts = 1
    for i in (1, 2):
        assert (
            rig.update(event(i, value=0, loss=(1, 1, 0, 0)))
            == library.values["complete"]
        )
    assert rig.policy.active_mask == 2 and rig.policy.attempts == 1
    for i in (3, 4):
        assert (
            rig.update(event(i, group=1, value=0, loss=(1, 1, 0, 0)))
            == library.values["complete"]
        )
    assert rig.policy.active_mask == 0 and rig.policy.attempts == 0


def test_stale_snapshot_never_erases_known_loss(library):
    rig = Rig(library)
    rig.update(event(3, group=1, loss=(1, 2, 0, 0)))
    rig.update(event(1, group=0, loss=(1, 1, 0, 0)))
    assert rig.policy.group[1].loss_token == 2
    before = bytes(rig.policy)
    rig.update(event(2, group=1, loss=(1, 1, 0, 0)))
    assert bytes(rig.policy) == before


@pytest.mark.parametrize("group", range(4))
@pytest.mark.parametrize("value", [0.0, 0.1, 1000.0])
def test_ineligible_policy_matches_one_ordinary_update(library, group, value):
    rig = Rig(library)
    item = event(1, group, value=value, qualified=False, loss=(0, 0, 0, 0))
    expected, work, outcome = clone(rig.state), Workspace(), Outcome()
    result = library.NavigationEskf_Update(
        expected, work, rig.filter, item.measurement, outcome
    )
    assert rig.update(item) == library.values["complete"]
    assert bytes(expected) == bytes(rig.state)
    assert bytes(outcome) == bytes(rig.output.filter)
    assert result == rig.output.filter.result


def test_empty_evidence_keeps_ordinary_update_semantics(library):
    rig = Rig(library)
    item = event(1, value=0)
    item.evidence = Evidence()
    assert rig.update(item) == library.values["complete"]


def test_invalid_mask_does_not_create_physical_baseline(library):
    rig = Rig(library)
    rig.packet(1, 1_000_000, physical_mask=255)
    assert all(g.last_physical_us == 0 for g in rig.receive.group)


def test_candidate_alias_is_rejected_without_authority_write(library):
    rig = Rig(library)
    item = event(1)
    before = bytes(rig.transaction)
    result = library.NavigationEskfRecovery_UpdateCandidate(
        rig.transaction.state,
        rig.transaction.policy,
        rig.work,
        rig.transaction,
        rig.filter,
        rig.config,
        item,
        rig.output,
    )
    assert result == library.values["invalid"] and bytes(rig.transaction) == before


def test_cooldown_is_global_and_boundary_inclusive(library):
    rig = Rig(library)
    arm(rig)
    rig.update(event(3))
    item = event(4)
    item.receive_us = 3_499_999
    rig.update(item)
    assert rig.policy.attempts == 1
    item = event(5)
    item.receive_us = 3_500_000
    rig.update(item)
    assert rig.policy.attempts == 2


def test_source_select_without_packet_breaks_chain_only(library):
    rig = Rig(library)
    rig.packet(1, 1_000_000)
    rig.packet(2, 3_000_000)
    chain = rig.receive.group[0].chain
    receipts = bytes(rig.receive.source)
    assert (
        library.NavigationEskfRecovery_SourceSelect(rig.receive, 1)
        == library.values["complete"]
    )
    assert all(g.stable_count == 0 for g in rig.receive.group)
    assert rig.receive.group[0].chain > chain and rig.receive.group[0].loss_token == 1
    assert bytes(rig.receive.source) == receipts


def test_reconstructed_prefix_and_repeated_fold_do_not_multiply_budget(library):
    full = Rig(library)
    for ordinal in (1, 2):
        full.update(event(ordinal))
    anchor_state, anchor_policy = clone(full.state), clone(full.policy)
    for ordinal in (3, 4, 5, 6):
        full.update(event(ordinal))
    expected = bytes(full.state), bytes(full.policy)
    for _ in range(6):
        rebuilt = Rig(library)
        rebuilt.state, rebuilt.policy = clone(anchor_state), clone(anchor_policy)
        receive_before = bytes(rebuilt.receive)
        for ordinal in (3, 4, 5, 6):
            rebuilt.update(event(ordinal))
        assert expected == (bytes(rebuilt.state), bytes(rebuilt.policy))
        assert bytes(rebuilt.receive) == receive_before and rebuilt.policy.attempts == 2


@pytest.mark.parametrize("index", range(8))
def test_null_arguments_do_not_touch_authority(library, index):
    rig = Rig(library)
    before = bytes(rig.state), bytes(rig.policy)
    args = [
        rig.state,
        rig.policy,
        rig.work,
        rig.transaction,
        rig.filter,
        rig.config,
        event(1),
        rig.output,
    ]
    args[index] = None
    assert (
        library.NavigationEskfRecovery_UpdateCandidate(*args)
        == library.values["invalid"]
    )
    assert before == (bytes(rig.state), bytes(rig.policy))


@pytest.mark.parametrize(
    "field,value",
    [("mission", 8), ("calibration", 12), ("source", 4), ("receive_us", 0)],
)
def test_update_identity_errors_do_not_publish(library, field, value):
    rig = Rig(library)
    item = event(1)
    setattr(item, field, value)
    assert rig.update(item) == library.values["invalid"]


def test_reset_clears_lifecycle_not_just_selected_source(library):
    rig = Rig(library)
    arm(rig)
    for source in range(4):
        rig.packet(10, 1_000_000 + source, source)
    assert (
        library.NavigationEskfRecovery_Reset(
            rig.receive, rig.policy, rig.config, 8, 12, 4_000_000
        )
        == library.values["complete"]
    )
    assert rig.receive.ordinal == 0 and not any(
        slot.valid for slot in rig.receive.source
    )
    assert (
        rig.policy.attempts == 0
        and rig.policy.active_mask == 0
        and not rig.policy.pending_valid
    )
    assert rig.receive.mission == 8 and rig.policy.calibration == 12


@pytest.mark.parametrize(
    "fault",
    ["pending_group", "pending_loss", "pending_chain", "active_loss", "streaks"],
)
def test_corrupt_policy_is_rejected_before_publication(library, fault):
    rig = Rig(library)
    arm(rig)
    if fault == "pending_group":
        rig.policy.pending_group = 4
    elif fault == "pending_loss":
        rig.policy.pending_loss += 1
    elif fault == "pending_chain":
        rig.policy.pending_chain += 1
    elif fault == "active_loss":
        rig.policy.group[3].loss_token = 0
    else:
        rig.policy.group[0].confirmations = 1
    rig.output.filter.result = library.values["ok"]
    rig.output.action = library.values["scaled"]
    assert rig.update(event(3)) == library.values["invalid"]
    assert (
        rig.output.filter.result == library.values["filter_invalid"]
        and rig.output.action == library.values["none"]
    )


@pytest.mark.parametrize("fault", ["chain", "count", "time", "outage"])
def test_corrupt_receive_state_cannot_mint_evidence(library, fault):
    rig = Rig(library)
    if fault == "chain":
        rig.receive.group[0].chain = 0
    elif fault == "count":
        rig.receive.group[0].stable_count = 200
    elif fault == "time":
        rig.receive.group[0].last_physical_us = 10_000_000
    else:
        rig.receive.group[0].in_outage = 1
    before = bytes(rig.receive)
    assert rig.packet(1, 1_000_000)[0] == library.values["invalid"]
    assert bytes(rig.receive) == before


def test_invalid_measurement_precedes_scale_numeric_fault(library):
    rig = Rig(library)
    arm(rig)
    rig.state.covariance[14][14] = math.nan
    item = event(3)
    item.measurement.variance[0] = -1
    expected, work, outcome = clone(rig.state), Workspace(), Outcome()
    assert (
        library.NavigationEskf_Update(
            expected, work, rig.filter, item.measurement, outcome
        )
        == library.values["filter_invalid"]
    )
    assert rig.update(item) != library.values["numeric"]
    assert bytes(rig.output.filter) == bytes(outcome)


@pytest.mark.parametrize(
    "fault",
    ["physical", "observation_nan", "observation_inf", "variance", "lever", "angular"],
)
@pytest.mark.parametrize("group", range(4))
def test_invalid_measurement_retains_original_outcome(library, fault, group):
    rig = Rig(library)
    item = event(1, group)
    if fault == "physical":
        item.measurement.physically_valid = 0
    elif fault == "observation_nan":
        item.measurement.observation[0] = math.nan
    elif fault == "observation_inf":
        item.measurement.observation[0] = math.inf
    elif fault == "variance":
        item.measurement.variance[0] = -1
    elif fault == "lever":
        item.measurement.lever_arm[2] = math.nan
    else:
        item.measurement.angular_rate[2] = math.inf
    expected, work, outcome = clone(rig.state), Workspace(), Outcome()
    library.NavigationEskf_Update(expected, work, rig.filter, item.measurement, outcome)
    assert rig.update(item) == library.values["measurement_invalid"]
    assert bytes(rig.output.filter) == bytes(outcome)


@pytest.mark.parametrize("group", [1, 3])
def test_unused_second_observation_does_not_block_valid_one_dimensional_update(
    library, group
):
    rig = Rig(library)
    item = event(1, group, value=0)
    item.measurement.observation[1] = math.nan
    item.measurement.variance[1] = math.inf
    assert rig.update(item) == library.values["complete"]
    assert rig.output.filter.result == library.values["ok"]


@pytest.mark.parametrize("seed", [0, 1, 7])
def test_scaled_accepted_update_matches_independent_dense_posterior(library, seed):
    rig = Rig(library, seed)
    arm(rig)
    prior = [
        [float(rig.state.covariance[i][j]) * 4 for j in range(15)] for i in range(15)
    ]
    s00, s11, s01 = prior[0][0] + 1, prior[1][1] + 1, prior[0][1]
    determinant = s00 * s11 - s01 * s01
    gains = [
        (
            (prior[i][0] * s11 - prior[i][1] * s01) / determinant,
            (prior[i][1] * s00 - prior[i][0] * s01) / determinant,
        )
        for i in range(15)
    ]
    expected = [
        [
            prior[i][j] - gains[i][0] * prior[0][j] - gains[i][1] * prior[1][j]
            for j in range(15)
        ]
        for i in range(15)
    ]
    assert rig.update(event(3, value=0)) == library.values["complete"]
    assert (
        rig.output.action == library.values["scaled"]
        and rig.output.filter.result == library.values["ok"]
    )
    assert rig.output.filter.gain_norm > 0 and rig.policy.group[0].confirmations == 1
    for i in range(15):
        for j in range(15):
            assert rig.state.covariance[i][j] == pytest.approx(
                expected[i][j], rel=3e-6, abs=1e-9
            )
            assert rig.state.covariance[i][j] == rig.state.covariance[j][i]
            assert rig.state.covariance[i][j] != 0
    lower = [[0.0] * 15 for _ in range(15)]
    for i in range(15):
        for j in range(i + 1):
            value = rig.state.covariance[i][j] - math.fsum(
                lower[i][k] * lower[j][k] for k in range(j)
            )
            if i == j:
                assert value > 0
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]


def test_float_no_change_is_limited_without_losing_ordinary_rejection(library):
    rig = Rig(library)
    arm(rig)
    # Experimental float32 subnormal edge, not target FPU-mode validation.
    for i in range(15):
        for j in range(15):
            rig.state.covariance[i][j] = 2**-149 if i == j else 0
    rig.config.scale[:] = [1 + 2**-23] * 15
    before = bytes(rig.state)
    assert rig.update(event(3)) == library.values["complete"]
    assert (
        rig.output.action == library.values["limited"]
        and rig.output.filter.result == library.values["nis"]
    )
    assert rig.policy.attempts == 1 and bytes(rig.state) == before
