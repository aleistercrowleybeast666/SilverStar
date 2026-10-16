"""Receive and deferred-fusion ownership through the actual health module."""
import ctypes as ct
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload'
PLATFORM = ROOT / 'apps/SCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
FIXTURE = Path(__file__).with_name('fixtures') / 'navigation_delayed_health.c'
OK, INVALID, VERIFY, BAD = 0, 5, 8, 9
START = 1_000_000


class Receive(ct.Structure):
    _fields_ = [('receive_us', ct.c_uint64), ('evaluation_us', ct.c_uint64), ('sequence', ct.c_uint32),
                ('variance_scale', ct.c_float), ('physically_valid', ct.c_uint8),
                ('source', ct.c_uint8), ('reason', ct.c_uint8)]


class Fusion(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in ('receive_us', 'measurement_us', 'evaluation_us')]
    _fields_ += [('sequence', ct.c_uint32), ('nis', ct.c_float), ('variance_scale', ct.c_float)]
    _fields_ += [(name, ct.c_uint8) for name in ('physically_valid', 'attempted', 'effective_update',
                                               'soft_weighted', 'reason', 'source')]


class Group(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in ('last_receive_us', 'last_physically_valid_us',
        'last_update_attempt_us', 'last_successful_fusion_us', 'last_recovery_us')]
    _fields_ += [('last_sequence', ct.c_uint32), ('recovery_count', ct.c_uint32),
                ('nis', ct.c_float), ('variance_scale', ct.c_float)]
    _fields_ += [(name, ct.c_uint8) for name in ('state', 'quality', 'reason', 'has_success', 'has_receive', 'source')]


class Health:
    def __init__(self, library):
        self.lib = library
        u8, u64 = ct.c_uint8, ct.c_uint64
        library.SystemNavigationHealth_Reset.argtypes = [u64]
        library.SystemNavigationHealth_DelayedReset.argtypes = [u64]
        library.SystemNavigationHealth_SourceSelect.argtypes = [u8, u8, u64]
        library.SystemNavigationHealth_SourceUnavailable.argtypes = [u8, u64]
        library.SystemNavigationHealth_ReceiveOnly.argtypes = [u8, ct.POINTER(Receive)]
        library.SystemNavigationHealth_FusionOnly.argtypes = [u8, ct.POINTER(Fusion)]
        library.SystemNavigationHealth_Observe.argtypes = [u8, ct.POINTER(Fusion)]
        library.SystemNavigationHealth_GroupGet.argtypes = [u8, u64, ct.POINTER(Group)]
        library.SystemNavigationHealth_OverallGet.argtypes = [u64, u8, ct.c_uint32]
        library.Test_HealthCapture.argtypes = [ct.POINTER(u8), ct.c_uint32]
        assert library.Test_HealthGroupSize() == ct.sizeof(Group) == 64

    def reset(self, delayed=True):
        (self.lib.SystemNavigationHealth_DelayedReset if delayed else self.lib.SystemNavigationHealth_Reset)(START)

    def select(self, source=0, now=START, group=0):
        return self.lib.SystemNavigationHealth_SourceSelect(group, source, now)

    def receive(self, sequence, receive, *, now=None, source=0, valid=1, scale=1., group=0):
        evidence = Receive(receive, receive if now is None else now, sequence, scale, valid, source, 3 if not valid else 0)
        return self.lib.SystemNavigationHealth_ReceiveOnly(group, ct.byref(evidence))

    def fusion(self, sequence, receive, source_time, now, *, source=0, reason=0, effective=1, nis=.5, group=0):
        evidence = Fusion(receive, source_time, now, sequence, nis, 1., 1, 1, effective, 0, reason, source)
        return self.lib.SystemNavigationHealth_FusionOnly(group, ct.byref(evidence))

    def group(self, now, group=0):
        value = Group()
        assert self.lib.SystemNavigationHealth_GroupGet(group, now, ct.byref(value)) == OK
        return value

    def capture(self):
        size = self.lib.Test_HealthCapture(None, 0)
        values = (ct.c_uint8 * size)()
        assert self.lib.Test_HealthCapture(values, size) == size
        return bytes(values)


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def health(request, tmp_path_factory):
    directory = tmp_path_factory.mktemp('delayed_health_' + request.param)
    source = CORE / 'System/Src/system_navigation_health.c'
    output = directory / 'health.dll'
    compiler = shutil.which('gcc')
    assert compiler
    command = [compiler, '-std=c11', request.param, '-Wall', '-Wextra', '-Werror', '-Wpedantic',
        '-Wconversion', '-Wsign-conversion', '-Wshadow', '-Wstrict-prototypes', '-Wmissing-prototypes',
        '-fno-fast-math', '-ffp-contract=off', '-shared', '-I' + str(CORE / 'System/Inc'),
        '-I' + str(CORE / 'Interfaces/Inc'), '-I' + str(CORE / 'Common/Inc'), '-I' + str(PLATFORM),
        '-DNAV_HEALTH_TEST_SOURCE="' + source.as_posix() + '"', str(FIXTURE),
        str(CORE / 'Common/Src/silverstar_assert.c'), '-lm', '-o', str(output)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (directory / 'compile.json').write_text(json.dumps(dict(command=command, exit_code=run.returncode,
        stdout=run.stdout, stderr=run.stderr,
        sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (source, CORE / 'System/Inc/system_navigation_health.h', FIXTURE)}), indent=2), encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
    result = Health(ct.CDLL(str(output)))
    yield result
    assert result.lib.Test_HealthLockErrors() == 0


def test_legacy_combined_interface_rejects_repeated_receipt_as_before(health):
    health.reset(delayed=False)
    evidence = Fusion(START + 100000, START + 50000, START + 100000, 1, math.nan, 1., 1, 0, 0, 0, 0, 0)
    assert health.lib.SystemNavigationHealth_Observe(0, ct.byref(evidence)) == OK
    evidence.evaluation_us = START + 600000
    evidence.attempted = evidence.effective_update = 1
    evidence.nis = .5
    assert health.lib.SystemNavigationHealth_Observe(0, ct.byref(evidence)) == BAD
    assert health.group(START + 600000).has_success == 0


def test_receive_and_fusion_times_and_sequences_stay_separate(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    assert health.receive(2, START + 200000) == OK
    assert health.group(START + 200000).has_success == 0
    assert health.fusion(1, START + 100000, START + 50000, START + 600000) == OK
    group = health.group(START + 600000)
    assert (group.last_receive_us, group.last_physically_valid_us, group.last_sequence) == (START + 200000, START + 200000, 2)
    assert group.last_successful_fusion_us == START + 600000 and group.state == 1
    before = health.capture()
    assert health.fusion(1, START + 100000, START + 50000, START + 600000) == BAD
    assert health.capture() == before
    assert health.fusion(2, START + 200000, START + 150000, START + 700000) == OK


def test_no_active_source_withdraws_without_inventing_a_receipt(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    assert health.receive(2, START + 200000) == OK
    assert health.fusion(1, START + 100000, START + 50000, START + 300000) == OK
    assert health.group(START + 300000).has_success == 1
    assert health.lib.SystemNavigationHealth_SourceUnavailable(0, START + 350000) == OK
    assert health.fusion(2, START + 200000, START + 150000, START + 400000) == OK
    group = health.group(START + 400000)
    assert group.has_success == group.has_receive == 0 and group.state == 4
    assert health.select(0, START + 450000) == OK
    assert health.receive(3, START + 500000) == OK
    assert health.fusion(3, START + 500000, START + 480000, START + 550000) == OK
    assert health.group(START + 550000).has_success == 1
    before = health.capture()
    assert health.lib.SystemNavigationHealth_SourceUnavailable(0, START + 540000) == BAD
    assert health.capture() == before


def test_source_switch_without_a_packet_and_returning_source_are_not_ready(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    assert health.fusion(1, START + 100000, START + 50000, START + 600000) == OK
    assert health.select(1, START + 650000) == OK
    group = health.group(START + 650000)
    assert group.source == 1 and group.has_success == group.has_receive == 0 and group.state == 4
    assert health.lib.SystemNavigationHealth_OverallGet(START + 650000, 1, 0) != 1
    assert health.receive(2, START + 700000, source=1) == OK
    assert health.fusion(2, START + 700000, START + 680000, START + 1200000, source=1) == OK
    assert health.select(0, START + 1250000) == OK
    before = health.capture()
    assert health.receive(1, START + 100000, now=START + 1250000) == BAD
    assert health.capture() == before
    assert health.receive(3, START + 1300000) == OK
    assert health.fusion(3, START + 1300000, START + 1280000, START + 1800000) == OK
    assert health.group(START + 1800000).state == 1


def test_old_source_completion_cannot_restore_new_source_health(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    assert health.select(1, START + 200000) == OK
    assert health.fusion(1, START + 100000, START + 50000, START + 600000) == OK
    group = health.group(START + 600000)
    assert group.source == 1 and group.has_success == group.has_receive == 0 and group.state == 4


def test_mission_recovery_diagnostics_survive_source_selection(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 2000000) == OK
    assert health.fusion(1, START + 2000000, START + 1950000, START + 2500000) == OK
    before = health.group(START + 2500000)
    assert before.recovery_count == 1 and before.last_recovery_us == START + 2500000
    assert health.select(1, START + 2600000) == OK
    after = health.group(START + 2600000)
    assert (after.recovery_count, after.last_recovery_us) == (before.recovery_count, before.last_recovery_us)
    assert after.has_success == 0 and after.source == 1


def test_latest_invalid_receipt_is_not_hidden_by_older_valid_completion(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    assert health.receive(2, START + 200000, valid=0) == OK
    assert health.fusion(1, START + 100000, START + 50000, START + 600000) == OK
    group = health.group(START + 600000)
    assert group.state == 3 and group.quality == 3 and group.has_success == 0
    assert health.receive(3, START + 700000) == OK
    assert health.group(START + 700000).state == 4
    assert health.fusion(3, START + 700000, START + 680000, START + 1200000) == OK
    assert health.group(START + 1200000).state == 1


def test_source_time_order_can_differ_from_receive_sequence_order(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 200000) == OK
    assert health.receive(2, START + 300000) == OK
    assert health.fusion(2, START + 300000, START + 25000, START + 600000) == OK
    assert health.fusion(1, START + 200000, START + 50000, START + 600000) == OK
    group = health.group(START + 600000)
    assert group.last_sequence == 2 and group.last_receive_us == START + 300000
    before = health.capture()
    assert health.fusion(2, START + 300000, START + 25000, START + 600000) == BAD
    assert health.capture() == before


def test_producer_sequence_rollover_is_normal(health):
    health.reset()
    assert health.select() == OK
    assert health.receive(0xffffffff, START + 100000) == OK
    assert health.receive(0, START + 200000) == OK
    assert health.fusion(0xffffffff, START + 100000, START + 50000, START + 600000) == OK
    assert health.fusion(0, START + 200000, START + 150000, START + 700000) == OK
    before = health.capture()
    assert health.receive(0xffffffff, START + 800000) == BAD
    assert health.capture() == before


def test_mixing_ownership_or_using_past_evaluation_is_an_ordinary_error(health):
    health.reset()
    assert health.select(now=START + 100000) == OK
    before = health.capture()
    evidence = Fusion(START + 50000, START + 25000, START + 100000, 1, .5, 1., 1, 1, 1, 0, 0, 0)
    assert health.lib.SystemNavigationHealth_Observe(0, ct.byref(evidence)) == BAD
    assert health.select(now=START + 99999) == BAD
    assert health.receive(1, START + 50000, now=START + 99999) == BAD
    assert health.capture() == before
    health.reset(delayed=False)
    assert health.select() == BAD


@pytest.mark.parametrize('kwargs,expected', [({'valid': 2}, INVALID), ({'scale': math.nan}, INVALID),
    ({'scale': .5}, INVALID), ({'source': 4}, INVALID), ({'group': 5}, INVALID),
    ({'source': 1}, BAD), ({'now': START + 50000}, INVALID)])
def test_bad_receive_keeps_all_authoritative_state_unchanged(health, kwargs, expected):
    health.reset()
    assert health.select() == OK
    before = health.capture()
    assert health.receive(1, START + 100000, **kwargs) == expected
    assert health.capture() == before


@pytest.mark.parametrize('kind,operation', [(1, 'select'), (2, 'receive'), (3, 'select'),
                                         (4, 'select'), (5, 'fusion')])
def test_internal_corruption_withdraws_health_and_does_not_resume(health, kind, operation):
    health.reset()
    assert health.select() == OK
    assert health.receive(1, START + 100000) == OK
    health.lib.Test_HealthCorrupt(kind)
    if operation == 'select': result = health.select(now=START + 200000)
    elif operation == 'receive': result = health.receive(2, START + 200000)
    else: result = health.fusion(1, START + 100000, START + 50000, START + 600000)
    assert result == VERIFY
    assert health.group(START + 600000).state == 6
    assert health.receive(3, START + 700000) == BAD
    assert health.lib.SystemNavigationHealth_OverallGet(START + 700000, 1, 0) == 4


def test_model_mismatch_stays_latched_across_packets_and_source_switch(health):
    health.reset()
    assert health.select() == OK
    health.lib.SystemNavigationHealth_ModelMismatchRecord()
    assert health.select(1, START + 100000) == BAD
    assert health.receive(1, START + 100000) == BAD
    snapshot = health.group(START - 1)
    assert snapshot.state == 6 and snapshot.reason == 5
