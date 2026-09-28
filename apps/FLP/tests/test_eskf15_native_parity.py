"""Actual C bounded rewind and native-window parity against float64 Python."""

from __future__ import annotations

import ctypes as ct
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_policy import StaggeredWindows
from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfState
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, DelayedReplay, Measurement
from tests.eskf15_c_bridge import (
    Body,
    CCore,
    Config,
    Float2,
    Float3,
    Observation,
    Outcome,
    State,
    Workspace,
)


class Event(ct.Structure):
    _fields_ = [
        ("measurement_us", ct.c_uint64),
        ("receive_us", ct.c_uint64),
        ("sequence", ct.c_uint32),
        ("source", ct.c_uint32),
        ("generation", ct.c_uint32),
        ("measurement", Observation),
    ]


class HistoryInput(ct.Structure):
    _fields_ = [
        ("end_us", ct.c_uint64),
        ("gyro", Float3 * 2),
        ("accel", Float3 * 2),
        ("dt_s", ct.c_float),
        ("quality_flags", ct.c_uint32),
    ]


class History(ct.Structure):
    _fields_ = [
        ("anchor", State),
        ("working", State),
        ("body", ct.POINTER(HistoryInput)),
        ("event", Event * 208),
        ("body_count", ct.c_uint16),
        ("event_count", ct.c_uint16),
        *[
            (name, ct.c_uint32)
            for name in (
                "replay_count",
                "history_misses",
                "overflows",
                "maximum_steps",
                "last_steps",
            )
        ],
    ]


class WindowConfig(ct.Structure):
    _fields_ = [
        ("length", ct.c_uint64),
        ("offset", ct.c_uint64),
        ("ttl", ct.c_uint64),
        ("gap", ct.c_uint32),
        ("threshold", ct.c_float),
        ("maximum", ct.c_float),
    ]


class WindowSample(ct.Structure):
    _fields_ = [
        ("epoch", ct.c_uint64),
        ("sequence", ct.c_uint32),
        ("source", ct.c_uint32),
        ("generation", ct.c_uint32),
        ("p", Float2),
        ("v", Float2),
        ("p_valid", ct.c_uint8),
        ("v_valid", ct.c_uint8),
    ]


class WindowState(ct.Structure):
    _fields_ = [
        ("start", ct.c_uint64),
        ("p", Float2),
        ("integral", Float2),
        ("p_count", ct.c_uint32),
        ("v_count", ct.c_uint32),
        ("started", ct.c_uint8),
        ("start_valid", ct.c_uint8),
    ]


class WindowContext(ct.Structure):
    _fields_ = [
        ("windows", WindowState * 2),
        ("previous", WindowSample),
        ("completed", ct.c_uint64),
        ("closure", Float2),
        ("norm", ct.c_float),
        ("scale", ct.c_float),
        ("complete_count", ct.c_uint32),
        ("unavailable_count", ct.c_uint32),
        ("previous_valid", ct.c_uint8),
        ("evidence_valid", ct.c_uint8),
        ("completed_start", ct.c_uint64),
        ("completed_covered", ct.c_uint32),
        ("completed_position_epochs", ct.c_uint32),
        ("completed_velocity_epochs", ct.c_uint32),
        ("completed_window_index", ct.c_uint8),
    ]


def _Replay_Create(native):
    core, history, storage = CCore(native, EskfState()), History(), (HistoryInput * 192)()
    signature = [ct.POINTER(History), ct.POINTER(State), ct.POINTER(Workspace), ct.POINTER(Config)]
    native.NavigationEskfReplay_Reset.argtypes = [
        ct.POINTER(History),
        ct.POINTER(State),
        ct.POINTER(HistoryInput),
    ]
    native.NavigationEskfReplay_Predict.argtypes = [*signature, ct.POINTER(Body)]
    native.NavigationEskfReplay_Insert.argtypes = [
        *signature,
        ct.POINTER(Event),
        ct.POINTER(Outcome),
    ]
    assert native.NavigationEskfReplay_Reset(ct.byref(history), ct.byref(core.state), storage) == 0
    return core, history, storage


def _Body_Create(start, duration, quality=0):
    return Body(
        (Float3 * 2)(Float3(), Float3()),
        (Float3 * 2)(Float3(0, 0, 9.78), Float3(0, 0, 9.78)),
        duration * 1e-6,
        start,
        start + duration,
        0,
        1,
        quality,
    )


def _PythonBody_Create(body):
    return BodyStep(
        body.start,
        body.end,
        np.array(body.gyro[0]),
        np.array(body.accel[0]),
        np.array(body.gyro[1]),
        np.array(body.accel[1]),
        0,
        1,
        body.quality,
    )


@pytest.mark.parametrize("failure", ["clipped", "nan", "covariance", "prefix_covariance"])
def test_prediction_rejection_at_trim_boundary_preserves_authoritative_history(native, failure):
    core, history, storage = _Replay_Create(native)
    args = [
        ct.byref(history),
        ct.byref(core.state),
        ct.byref(core.workspace),
        ct.byref(core.config),
    ]
    python = DelayedReplay(Eskf15Filter(), 1_000_000)
    for _index in range(60):
        body = _Body_Create(core.state.timestamp, 10_000)
        assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 0
        python.Body_Receive(_PythonBody_Create(body))
    body = _Body_Create(core.state.timestamp, 10_000)
    if failure == "clipped":
        body.quality = 2
    elif failure == "nan":
        body.accel[0][0] = np.nan
    elif failure == "covariance":
        core.state.covariance[0][0] = -1e6
        python.kernel.state.covariance[0, 0] = -1e6
    else:
        history.anchor.covariance[0][0] = -1e6
    before = (
        bytes(core.state),
        bytes(history.anchor),
        bytes(storage),
        bytes(history.event),
        history.body_count,
        history.event_count,
    )
    assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 5
    assert (
        bytes(core.state),
        bytes(history.anchor),
        bytes(storage),
        bytes(history.event),
        history.body_count,
        history.event_count,
    ) == before
    if failure != "prefix_covariance":
        py_before = python.kernel.state.State_Clone()
        present, base, count = python.present_us, python.base_us, len(python.steps)
        with pytest.raises(ValueError):
            python.Body_Receive(_PythonBody_Create(body))
        assert (python.present_us, python.base_us, len(python.steps)) == (present, base, count)
        np.testing.assert_array_equal(python.kernel.state.covariance, py_before.covariance)


def test_multiple_prefix_commit_and_capacity_rejection_are_bounded(native, tmp_path):
    core, history, storage = _Replay_Create(native)
    args = [
        ct.byref(history),
        ct.byref(core.state),
        ct.byref(core.workspace),
        ct.byref(core.config),
    ]
    python = DelayedReplay(Eskf15Filter(), 1_000_000)
    for _index in range(60):
        body = _Body_Create(core.state.timestamp, 10_000)
        assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 0
        python.Body_Receive(_PythonBody_Create(body))
    event = Event(
        1_005_000,
        core.state.timestamp,
        1,
        0,
        1,
        Observation(0, 1, Float2(0.01, -0.01), Float2(1, 1), Float3(), Float3()),
    )
    outcome = Outcome()
    assert native.NavigationEskfReplay_Insert(*args, ct.byref(event), ct.byref(outcome)) == 0
    python.Measurement_Receive(
        Measurement(
            (1, 0),
            event.measurement_us,
            event.receive_us,
            0,
            np.array([0.01, -0.01]),
            np.ones(2),
            True,
            generation=1,
        )
    )
    body = _Body_Create(core.state.timestamp, 20_000)
    assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 0
    python.Body_Receive(_PythonBody_Create(body))
    assert history.anchor.timestamp == 1_020_000 and history.body_count == 59
    assert history.event_count == 0
    for name in ("p", "v", "q", "bg", "ba", "covariance"):
        np.testing.assert_allclose(
            np.ctypeslib.as_array(getattr(core.state, name)),
            getattr(python.kernel.state, name),
            atol=2e-4,
            rtol=3e-4,
        )
    core, history, storage = _Replay_Create(native)
    args = [
        ct.byref(history),
        ct.byref(core.state),
        ct.byref(core.workspace),
        ct.byref(core.config),
    ]
    python = DelayedReplay(Eskf15Filter(), 1_000_000, max_steps=192)
    for _index in range(192):
        body = _Body_Create(core.state.timestamp, 2_000)
        assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 0
        python.Body_Receive(_PythonBody_Create(body))
    before = bytes(core.state), bytes(history.anchor), bytes(storage), history.body_count
    body = _Body_Create(core.state.timestamp, 2_000)
    assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 3
    assert (bytes(core.state), bytes(history.anchor), bytes(storage), history.body_count) == before
    with pytest.raises(ValueError, match="capacity"):
        python.Body_Receive(_PythonBody_Create(body))
    assert len(python.steps) == 192 and python.present_us == core.state.timestamp
    (tmp_path / "transaction_boundaries.json").write_text(
        json.dumps(
            {
                "rejected_before_trim": ["CLIPPED", "NaN", "live_non_PSD", "prefix_non_PSD"],
                "authoritative_state_and_history_unchanged": True,
                "successful_multiple_prefix_count": 2,
                "capacity": 192,
                "capacity_failure_preserves_state": True,
                "additional_global_or_full_state_storage": 0,
            }
        ),
        encoding="utf8",
    )


@pytest.fixture
def native(tmp_path):
    selected = os.environ.get("SILVERSTAR_FCCG_ROOT")
    if not selected:
        pytest.skip("actual FCCG source must be explicitly selected")
    root = Path(selected) / "plugins/builtin"
    core = root / "silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
    quality = root / "silverstar_algorithm_common/payload/Algorithm/Common"
    common = root / "silverstar_core_0_0_12/payload/Common"
    dll = tmp_path / "native.dll"
    command = [
        shutil.which("gcc"),
        "-shared",
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static-libgcc",
        "-I",
        str(core / "Inc"),
        "-I",
        str(quality / "Inc"),
        "-I",
        str(common / "Inc"),
        str(common / "Src/silverstar_assert.c"),
        str(core / "Src/navigation_eskf.c"),
        str(core / "Src/navigation_eskf_replay.c"),
        str(quality / "Src/navigation_quality.c"),
        "-o",
        str(dll),
        "-lm",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path)),
    )
    assert result.returncode == 0, result.stderr
    return ct.CDLL(str(dll))


@pytest.mark.parametrize("interval_us", [10_000, 4_000])
def test_actual_c_mid_interval_delayed_replay(native, tmp_path, interval_us):
    c = CCore(native, EskfState())
    history = History()
    native.NavigationEskfReplay_Reset.argtypes = [
        ct.POINTER(History),
        ct.POINTER(State),
        ct.POINTER(HistoryInput),
    ]
    signature = [ct.POINTER(History), ct.POINTER(State), ct.POINTER(Workspace), ct.POINTER(Config)]
    native.NavigationEskfReplay_Predict.argtypes = [*signature, ct.POINTER(Body)]
    native.NavigationEskfReplay_Insert.argtypes = [
        *signature,
        ct.POINTER(Event),
        ct.POINTER(Outcome),
    ]
    assert ct.sizeof(HistoryInput) == 64
    body_storage = (HistoryInput * 192)()
    assert (
        native.NavigationEskfReplay_Reset(ct.byref(history), ct.byref(c.state), body_storage) == 0
    )
    python = DelayedReplay(Eskf15Filter(), 1_000_000)
    maximum = 0.0
    for index in range(200):
        start = 1_000_000 + index * interval_us
        end = start + interval_us
        w1, w2 = np.array([0.04, -0.03, 0.06]), np.array([-0.02, 0.05, 0.04])
        a1, a2 = np.array([0.2, -0.1, 9.79]), np.array([-0.3, 0.2, 9.77])
        body = Body(
            (Float3 * 2)(Float3(*w1), Float3(*w2)),
            (Float3 * 2)(Float3(*a1), Float3(*a2)),
            interval_us * 1e-6,
            start,
            end,
            0,
            1,
            0,
        )
        args = [ct.byref(history), ct.byref(c.state), ct.byref(c.workspace), ct.byref(c.config)]
        assert native.NavigationEskfReplay_Predict(*args, ct.byref(body)) == 0
        python.Body_Receive(BodyStep(start, end, w1, a1, w2, a2, 0, 1))
        if index > 5 and index % 11 == 0:
            group = (index // 11) % 5
            dimension = 2 if group in (0, 2) else 1
            z, r = np.full(dimension, 0.025), np.ones(dimension)
            observation = Observation(
                group,
                1,
                Float2(*([0.025] * dimension)),
                Float2(*([1.0] * dimension)),
                Float3(),
                Float3(*w1),
            )
            event = Event(end - 23_000, end, index, 0, 1, observation)
            outcome = Outcome()
            assert (
                native.NavigationEskfReplay_Insert(*args, ct.byref(event), ct.byref(outcome)) == 0
            )
            result = python.Measurement_Receive(
                Measurement((index, group), end - 23_000, end, group, z, r, True, generation=1)
            )
            assert outcome.result == int(result.result)
        for name in ("p", "v", "q", "bg", "ba", "covariance"):
            actual = np.ctypeslib.as_array(getattr(c.state, name))
            expected = getattr(python.kernel.state, name)
            maximum = max(maximum, float(np.max(np.abs(actual - expected))))
            np.testing.assert_allclose(actual, expected, atol=2e-4, rtol=3e-4)
        assert history.body_count <= 600_000 // interval_us
    (tmp_path / "delayed_parity.json").write_text(
        json.dumps(
            {
                "epochs": 200,
                "interval_us": interval_us,
                "mid_interval_events": history.replay_count,
                "maximum_absolute_error": maximum,
                "maximum_c_replay_steps": history.maximum_steps,
            }
        ),
        encoding="utf8",
    )


def test_actual_c_windows_gaps_duplicates_late_epochs_and_ttl(native, tmp_path):
    config, context = (
        WindowConfig(10_000_000, 5_000_000, 6_000_000, 120_000, 10.0, 4.0),
        WindowContext(),
    )
    native.NavigationWindow_Receive.argtypes = [
        ct.POINTER(WindowContext),
        ct.POINTER(WindowConfig),
        ct.POINTER(WindowSample),
    ]
    native.NavigationWindow_VarianceScale.argtypes = [
        ct.POINTER(WindowContext),
        ct.POINTER(WindowConfig),
        ct.c_uint64,
    ]
    native.NavigationWindow_VarianceScale.restype = ct.c_float
    python = StaggeredWindows()
    maximum, completed = 0.0, 0
    for index in range(750):
        timestamp = 1_000_000 + index * 100_000 + (300_000 if index >= 320 else 0)
        elapsed = (timestamp - 1_000_000) * 1e-6
        p, v = (elapsed * 2.5, elapsed * 0.3), (1.0, 0.2)
        valid = index not in (200, 600)
        sample = WindowSample(timestamp, index, 0, 1, Float2(*p), Float2(*v), valid, 1)
        native.NavigationWindow_Receive(ct.byref(context), ct.byref(config), ct.byref(sample))
        completed += len(
            python.Sample_Receive(
                timestamp,
                np.array(p),
                np.array(v),
                position_valid=valid,
                velocity_valid=True,
                source=0,
                generation=1,
                sequence=index,
            )
        )
        actual = native.NavigationWindow_VarianceScale(
            ct.byref(context), ct.byref(config), timestamp
        )
        maximum = max(maximum, abs(actual - python.VarianceScale_Get(timestamp)))
        assert actual == pytest.approx(python.VarianceScale_Get(timestamp), abs=3e-4)
        if index in (150, 450):
            before = bytes(context)
            sample.epoch -= 1
            assert (
                native.NavigationWindow_Receive(
                    ct.byref(context), ct.byref(config), ct.byref(sample)
                )
                == 2
            )
            assert bytes(context) == before
            python.Sample_Receive(
                timestamp - 1,
                np.array(p),
                np.array(v),
                position_valid=valid,
                velocity_valid=True,
                source=0,
                generation=1,
                sequence=index,
            )
    expired = timestamp + 6_000_001
    assert (
        native.NavigationWindow_VarianceScale(ct.byref(context), ct.byref(config), expired) == 1.0
    )
    assert python.VarianceScale_Get(expired) == 1.0
    (tmp_path / "window_parity.json").write_text(
        json.dumps(
            {
                "samples": 750,
                "completed_windows": completed,
                "maximum_scale_error": maximum,
                "gap_reset_count": python.reset_count,
            }
        ),
        encoding="utf8",
    )
