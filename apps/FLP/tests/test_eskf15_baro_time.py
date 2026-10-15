"""Barometer What-if timing against the actual owning C time resolver."""

from __future__ import annotations

import ctypes as ct
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfUpdateResult
from silverstar_flp.plugins.algorithms.eskf15.plugin import Eskf15AlgorithmPlugin
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, DelayedReplay
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest


@pytest.fixture(scope="module", params=("-O0", "-O2"))
def c_resolve(tmp_path_factory, request):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("actual C SystemTime resolver requires GCC")
    root = Path(__file__).resolve().parents[3]
    plugins = root / "apps/SCG/plugins/builtin"
    core = plugins / "silverstar_core_0_1_0/payload"
    platform = plugins / "silverstar_platform_api/payload/Platform/Inc"
    output = tmp_path_factory.mktemp("baro_time_" + request.param[1:])
    stub = output / "unused_platform.c"
    stub.write_text(
        r"""
#include <stdlib.h>
#include "platform_time.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
PlatformResult PlatformTime_Init(void) { abort(); }
uint64_t PlatformTime_Us(void) { abort(); }
PlatformCriticalState PlatformCritical_Enter(void) { abort(); }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; abort(); }
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ (void)condition; (void)module; (void)file; (void)line; (void)reason; abort(); }
void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line)
{ (void)object; (void)alignment; (void)module; (void)file; (void)line; abort(); }
""",
        encoding="utf-8",
    )
    library = output / "system_time.dll"
    command = [compiler, "-std=c11", request.param, "-Wall", "-Wextra", "-Werror",
               "-shared", str(core / "System/Src/system_time.c"), str(stub),
               "-o", str(library)]
    for directory in (core / "System/Inc", core / "Interfaces/Inc",
                      core / "Common/Inc", platform):
        command.extend(("-I", str(directory)))
    compiled = subprocess.run(command, capture_output=True, text=True, check=False)
    (output / "compile.json").write_text(json.dumps({
        "command": command, "returncode": compiled.returncode,
        "stdout": compiled.stdout, "stderr": compiled.stderr,
        "compiler_version": subprocess.check_output([compiler, "--version"], text=True),
    }, indent=2), encoding="utf-8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    native = ct.CDLL(str(library))
    function = native.SystemTime_MeasurementTimestampResolve
    function.argtypes = [ct.c_uint64, ct.c_uint64, ct.c_uint8, ct.c_uint32,
                         ct.POINTER(ct.c_uint64)]
    function.restype = ct.c_int

    def resolve(receive, sample, trusted, delay):
        # Backend_BarometerUpdate zero-initializes its event before this call.
        timestamp = ct.c_uint64(0)
        result = function(receive, sample, trusted, delay, ct.byref(timestamp))
        return result, timestamp.value

    return resolve


def _Dataset_Create(path, *, receive=2_000_000, sample=1_900_000, trusted=1,
                    evaluation=2_000_000, recorded=1_800_000):
    payload = dict(
        sample_timestamp_us=sample, receive_timestamp_us=receive,
        measurement_timestamp_us=recorded, evaluation_timestamp_us=evaluation,
        estimator_present_timestamp_us=evaluation, operation_sequence=5,
        source_id=0, calibration_generation=1, group=4, physically_valid=1,
        observation=(0.1, 0.0), base_variance=(1.0, 0.0),
        quality_scale=1.0, consistency_scale=1.0, relative_altitude_m=0.1,
        valid_mask=1, measurement_timestamp_trusted=trusted,
    )
    native = dict(sample_timestamp_us=sample, receive_timestamp_us=receive,
                  measurement_timestamp_trusted=trusted, sequence=7, instance_id=0)
    records = {"BARO_NATIVE": (SimpleNamespace(payload=native, record_sequence=2),)}
    if path == "eskf":
        # This wire record does not carry the timestamp trust flag.
        del payload["measurement_timestamp_trusted"]
        records["ESKF15_MEASUREMENT"] = (SimpleNamespace(payload=payload, record_sequence=3),)
    else:
        records["BARO_MEASUREMENT"] = (SimpleNamespace(payload=payload, record_sequence=3),)
    return SimpleNamespace(
        Records_Get=lambda name: records.get(name, ()), records=records,
        initial_state=SimpleNamespace(payload={}),
    )


def _Build(dataset, delay, *, mode=ReplayMode.WHAT_IF, override=True):
    parameters = {"baro_measurement_delay_ms": delay, "baro_std_m": 1.0}
    request = ReplayRequest(mode=mode, parameters=(
        {"baro_measurement_delay_ms": delay} if override else {}))
    events, _, _ = Eskf15AlgorithmPlugin()._Measurements_Build(
        dataset, parameters, 0, 3_000_000, request)
    assert len(events) == 1
    return events[0][2]


@pytest.mark.parametrize("path", ("eskf", "legacy"))
@pytest.mark.parametrize("trusted", (0, 1))
@pytest.mark.parametrize("delay", (0, 100, 550))
def test_baro_override_matches_actual_c_without_double_delay(c_resolve, path, trusted, delay):
    dataset = _Dataset_Create(path, trusted=trusted)
    before = deepcopy(dataset.records)
    result, expected = c_resolve(2_000_000, 1_900_000, trusted, delay)
    item = _Build(dataset, delay)
    assert result == 0
    assert item.timestamp_us == expected
    assert item.receive_us == 2_000_000
    assert item.physically_valid
    assert dataset.records == before


@pytest.mark.parametrize("path", ("eskf", "legacy"))
@pytest.mark.parametrize("receive,sample,trusted,delay", (
    (0, 0, 0, 0), (2_000_000, 0, 1, 100),
    (2_000_000, 2_000_001, 1, 100), (50_000, 40_000, 0, 100),
    (2_000_000, 1_900_000, 2, 100),
))
def test_invalid_baro_resolution_matches_c_zero_event_and_cannot_fuse(
    c_resolve, path, receive, sample, trusted, delay,
):
    result, expected = c_resolve(receive, sample, trusted, delay)
    assert result != 0 and expected == 0
    item = _Build(_Dataset_Create(path, receive=receive, sample=sample, trusted=trusted), delay)
    assert item.timestamp_us == expected
    assert not item.physically_valid


@pytest.mark.parametrize("path", ("eskf", "legacy"))
def test_untrusted_origin_boundary_matches_c_and_remains_history_miss(c_resolve, path):
    result, expected = c_resolve(100_000, 0, 0, 100)
    assert (result, expected) == (0, 0)
    item = _Build(_Dataset_Create(path, receive=100_000, sample=0, trusted=0), 100)
    assert item.timestamp_us == 0
    replay = DelayedReplay(Eskf15Filter(), 100_000)
    assert replay.Measurement_Receive(item).result == EskfUpdateResult.HISTORY_MISS


@pytest.mark.parametrize("sample,receive,expected", (
    (1_399_999, 2_000_000, EskfUpdateResult.HISTORY_MISS),
    (1_400_000, 2_000_000, EskfUpdateResult.HISTORY_MISS),
    (1_400_001, 2_000_000, EskfUpdateResult.ACCEPTED),
    (2_000_000, 2_000_000, EskfUpdateResult.ACCEPTED),
    (2_000_000, 2_000_001, EskfUpdateResult.TIMING_INVALID),
))
def test_trusted_history_edges_and_future_receive_keep_replay_guards(
    c_resolve, sample, receive, expected,
):
    result, timestamp = c_resolve(receive, sample, 1, 100)
    assert result == 0
    item = _Build(_Dataset_Create("eskf", receive=receive, sample=sample), 100)
    assert item.timestamp_us == timestamp
    replay = DelayedReplay(Eskf15Filter(), 1_000_000)
    zero, gravity = np.zeros(3), np.array([0.0, 0.0, 9.78])
    for start in range(1_000_000, 2_000_000, 10_000):
        replay.Body_Receive(BodyStep(start, start + 10_000, zero, gravity, zero, gravity))
    assert replay.base_us == 1_400_000
    before = replay.kernel.state.State_Clone()
    assert replay.Measurement_Receive(item).result == expected
    if expected != EskfUpdateResult.ACCEPTED:
        np.testing.assert_array_equal(replay.kernel.state.p, before.p)
        np.testing.assert_array_equal(replay.kernel.state.covariance, before.covariance)


@pytest.mark.parametrize("mode,override", (
    (ReplayMode.RECORDED_CONFIGURATION, False),
    (ReplayMode.RECORDED_CONFIGURATION, True),
    (ReplayMode.WHAT_IF, False),
))
def test_recorded_timestamp_is_not_reinterpreted_without_what_if_override(mode, override):
    dataset = _Dataset_Create("eskf", recorded=1_700_123)
    dataset.records.pop("BARO_NATIVE")
    before = deepcopy(dataset.records)
    item = _Build(dataset, 550, mode=mode, override=override)
    assert item.timestamp_us == 1_700_123
    assert item.physically_valid
    assert dataset.records == before


@pytest.mark.parametrize("case", ("missing", "duplicate", "wrong_sample", "missing_flag"))
def test_eskf_baro_override_requires_unique_timestamp_trust_evidence(case):
    dataset = _Dataset_Create("eskf")
    native = dataset.records["BARO_NATIVE"][0]
    if case == "missing":
        dataset.records.pop("BARO_NATIVE")
    elif case == "duplicate":
        dataset.records["BARO_NATIVE"] = (native, deepcopy(native))
    elif case == "wrong_sample":
        native.payload["sample_timestamp_us"] -= 1
    else:
        native.payload.pop("measurement_timestamp_trusted")
    with pytest.raises(ValueError, match="eskf15_what_if_timestamp_trust_evidence_missing"):
        _Build(dataset, 100)
