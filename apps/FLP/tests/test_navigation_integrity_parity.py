"""Opt-in cross-repository C/Python revision-2 GNSS decision parity."""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.gnss_integrity_stream import IntegrityStream


def test_c_receiver_native_stream_matches_python_at_every_epoch(tmp_path: Path) -> None:
    root_text = os.environ.get("SILVERSTAR_FCCG_ROOT")
    gcc = shutil.which("gcc")
    if not root_text or not gcc:
        pytest.skip("set SILVERSTAR_FCCG_ROOT and provide host GCC for joint gate")
    root = Path(root_text)
    kf6 = (
        root
        / "plugins/builtin/silverstar_algorithm_estimator_kf6"
        / "payload/Algorithm/Estimator/KF6"
    )
    common = root / "plugins/builtin/silverstar_core_0_0_12/payload/Common"
    executable = tmp_path / "integrity-trace.exe"
    command = [
        gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I" + str(kf6 / "Inc"), "-I" + str(common / "Inc"),
        str(kf6 / "Src/navigation_integrity.c"),
        str(common / "Src/silverstar_assert.c"),
        str(root / "tests/fixtures/navigation_integrity_host.c"),
        "-lm", "-o", str(executable),
    ]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
    completed = subprocess.run([str(executable), "trace"], check=True,
                               capture_output=True, text=True, env=environment)
    rows = list(csv.reader(completed.stdout.splitlines()))
    assert len(rows) == 600
    stream = IntegrityStream({"gnss_integrity_recovery_duration_ms": 1000})
    states = set()
    for row in rows:
        (timestamp, epoch, sequence, source, mask) = map(int, row[:5])
        east, north, east_velocity, north_velocity, hacc, sacc = map(float, row[5:11])
        state, admitted = map(int, row[11:13])
        scale, closure = map(float, row[13:15])
        reset, reason, evidence = map(int, row[15:18])
        decision = stream.Receive(
            timestamp_us=timestamp, epoch=epoch, sequence=sequence,
            source=source, mask=mask,
            position=np.asarray((east, north), dtype=np.float32),
            velocity=np.asarray((east_velocity, north_velocity), dtype=np.float32),
            hacc=hacc, sacc=sacc,
        )
        assert (decision.state, decision.admitted_mask, decision.chain_reset,
                decision.reason, decision.evidence_valid) == (
                state, admitted, bool(reset), reason, bool(evidence))
        assert decision.position_r_scale == pytest.approx(scale)
        if evidence:
            assert decision.closure_norm_m == pytest.approx(closure, abs=1e-3)
        states.add(state)
    assert states == {0, 1, 2}
