from __future__ import annotations

import ctypes as ct
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.eskf15.filter import (
    Eskf15Filter,
    EskfState,
    Rotation_Exp,
)
from tests.eskf15_c_bridge import CCore


@pytest.mark.skipif(
    not os.environ.get("SILVERSTAR_FCCG_ROOT"),
    reason="actual FCCG C source must be explicitly provided",
)
def test_actual_c_float32_against_float64_reference(tmp_path):
    root = Path(os.environ["SILVERSTAR_FCCG_ROOT"])
    core = (
        root
        / "plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
    )
    compiler = shutil.which("gcc")
    common = root / "plugins/builtin/silverstar_core_0_0_12/payload/Common"
    assert compiler, "Host GCC required"
    dll = tmp_path / "eskf15.dll"
    build = subprocess.run(
        [
            compiler,
            "-shared",
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static-libgcc",
            "-I",
            str(core / "Inc"),
            "-I",
            str(common / "Inc"),
            str(common / "Src/silverstar_assert.c"),
            str(core / "Src/navigation_eskf.c"),
            "-o",
            str(dll),
            "-lm",
        ],
        capture_output=True,
        text=True,
        env=dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path)),
    )
    assert build.returncode == 0, build.stdout + build.stderr
    library = ct.CDLL(str(dll))
    rng = np.random.default_rng(67109)
    maximum = {name: 0.0 for name in ("p", "v", "q", "bg", "ba", "covariance", "nis")}
    for scenario in range(4):
        initial = EskfState(q=Rotation_Exp(np.array([0.02, -0.01, 0.04]) * scenario))
        python = Eskf15Filter(initial)
        c = CCore(library, initial)
        for index in range(500):
            t = index * 0.01
            gyro = np.array([0.1 * np.sin(t), 0.15 * np.cos(t * 0.7), 0.05]) * scenario
            accel = np.array([0.1 * np.cos(t), 0.2 * np.sin(t), 9.78])
            w1, w2 = gyro + rng.normal(0, 0.0001, 3), gyro + rng.normal(0, 0.0001, 3)
            a1, a2 = accel + rng.normal(0, 0.001, 3), accel + rng.normal(0, 0.001, 3)
            assert c.Predict(w1, a1, w2, a2) == 0
            python.Prediction_ApplyPair(w1, a1, 0.005, w2, a2, 0.005)
            if index % 10 == 0:
                for group, axes in enumerate(((0, 1), (2,), (0, 1), (2,), (2,))):
                    kind = "velocity" if group in (2, 3) else "position"
                    lever = (
                        np.array([0.2, -0.1, 0.3]) if scenario == 3 and group != 4 else np.zeros(3)
                    )
                    z, _ = python.Measurement_Model(kind, axes, lever)
                    z += rng.normal(0, 0.1, len(axes))
                    r = np.full(len(axes), 0.2 if group in (2, 3) else 2.0)
                    c_result, outcome = c.Update(group, z, r, (w1 + w2) * 0.5, lever)
                    result = python.Measurement_Apply(
                        kind,
                        axes,
                        z,
                        r,
                        lever_arm=lever,
                        soft=(6.635, 9.21)[len(axes) - 1],
                        hard=(10.828, 13.816)[len(axes) - 1],
                        max_scale=4.0,
                    )
                    assert c_result == int(result.result), (scenario, index, group)
                    maximum["nis"] = max(maximum["nis"], abs(outcome.nis - result.nis))
                    np.testing.assert_allclose(outcome.nis, result.nis, atol=2e-4, rtol=3e-4)
            for name in ("p", "v", "q", "bg", "ba", "covariance"):
                actual = np.ctypeslib.as_array(getattr(c.state, name))
                expected = getattr(python.state, name)
                error = float(np.max(np.abs(actual - expected)))
                maximum[name] = max(maximum[name], error)
                # Float32 accumulation over 500 steps vs independent float64.
                # Absolute tolerance is sub-mm/sub-mrad, not metres/degrees.
                np.testing.assert_allclose(
                    actual, expected, atol=2e-4, rtol=3e-4, err_msg=f"{scenario}/{index}/{name}"
                )
    (tmp_path / "parity.json").write_text(
        json.dumps(
            {
                "maximum_absolute_error": maximum,
                "scenarios": 4,
                "prediction_epochs": 2000,
                "measurement_groups": 1000,
                "tolerance": {"absolute": 2e-4, "relative": 3e-4},
            },
            indent=2,
        ),
        encoding="utf8",
    )
