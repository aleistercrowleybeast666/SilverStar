from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.kf6.filter import (
    Kf6Filter,
    Kf6GnssEpoch,
    Kf6GnssGroup,
    Kf6UpdateResult,
)


def Filter_Create(outage_ms=300):
    return Kf6Filter.Kf6_Create(
        process_accel_std_mps2=np.array([1.5, 1.5, 2]),
        p0_diagonal=np.array([4, 4, 9, 0.25, 0.25, 0.25]),
        initial_velocity_enu_mps=np.zeros(3),
        nis_soft_threshold=np.array([6.635, 9.210, 11.345]),
        nis_hard_threshold=np.array([10.828, 13.816, 16.266]),
        nis_max_r_scale=10,
        gnss_reacquire_outage_ms=outage_ms,
    )


def Epoch_Create(timestamp, mask=15, invalid=False):
    std = np.full(3, 0.2, dtype=np.float32)
    if invalid:
        std[2] = np.nan
    return Kf6GnssEpoch(
        timestamp,
        np.zeros(3, dtype=np.float32),
        np.zeros(3, dtype=np.float32),
        np.ones(3, dtype=np.float32),
        std,
        mask,
    )


def test_c_python_same_float32_inputs_all_outage_scenarios(tmp_path):
    expected = np.asarray(
        json.loads((Path(__file__).parent / "fixtures/kf6_outage_vectors.json").read_text())[
            "rows"
        ],
        dtype=np.float64,
    )
    rows = []
    for scenario in range(10):
        kf = Filter_Create()
        kf.Kf6_GnssEpochTrack(Epoch_Create(1000000))
        if scenario not in (2, 8):
            kf.state[[0, 2, 3, 5]] = -30
        for step in range(64):
            gap = 100000 if scenario == 1 else (500000 if scenario in (2, 3, 7) else 40000)
            timestamp = 1000000 + gap + step * 40000
            mask = 15
            if scenario in (4, 6) and step < 12:
                mask = 7
            if scenario == 5 and step < 12:
                mask = 3
            if scenario == 6 and 20 <= step < 32:
                mask = 7
            if scenario == 7:
                if step == 2:
                    timestamp = 0
                if step == 4:
                    timestamp -= 40000
                if step == 6:
                    timestamp = 1000000
            if scenario == 8:
                kf.Kf6_Predict(np.array([0.012, -0.006, 0.009], dtype=np.float32), 0.04)
                kf.Kf6_UpdateBaro(0.2, 4)
            epoch = Epoch_Create(timestamp, mask, scenario == 9 and step < 12)
            kf.Kf6_GnssEpochTrack(epoch)
            pr = kf.Kf6_UpdateGnssPosition(epoch.position_enu_m, np.ones(3, dtype=np.float32))
            kf.Kf6_GnssGroupResultProcess(Kf6GnssGroup.POSITION_HORIZONTAL, pr.horizontal_result)
            kf.Kf6_GnssGroupResultProcess(Kf6GnssGroup.POSITION_VERTICAL, pr.vertical_result)
            if mask & 4:
                vr = kf.Kf6_UpdateGnssVelocity(
                    epoch.velocity_enu_mps,
                    np.full(3, 0.04, dtype=np.float32),
                    vertical_valid=bool(mask & 8),
                )
                kf.Kf6_GnssGroupResultProcess(
                    Kf6GnssGroup.VELOCITY_HORIZONTAL, vr.horizontal_result
                )
                if mask & 8:
                    kf.Kf6_GnssGroupResultProcess(
                        Kf6GnssGroup.VELOCITY_VERTICAL, vr.vertical_result
                    )
            row = [scenario, step, *kf.state, *kf.covariance.ravel()]
            for state in kf._reacquire_groups:
                row.extend(
                    [
                        state.outage,
                        state.inflation_attempt_count,
                        state.reject_streak,
                        state.consistent_count,
                    ]
                )
            rows.append(row)
    actual = np.asarray(rows, dtype=np.float64)
    errors = {
        "max_position_m": float(np.max(abs(actual[:, 2:5] - expected[:, 2:5]))),
        "max_velocity_mps": float(np.max(abs(actual[:, 5:8] - expected[:, 5:8]))),
        "max_covariance": float(np.max(abs(actual[:, 8:44] - expected[:, 8:44]))),
    }
    (tmp_path / "c_python_equivalence.json").write_text(json.dumps(errors, indent=2))
    np.testing.assert_allclose(actual[:, 2:44], expected[:, 2:44], rtol=2e-5, atol=2e-5)
    np.testing.assert_array_equal(actual[:, 44:], expected[:, 44:])


@pytest.mark.parametrize("outage_ms", [160, 200, 250, 300, 500])
def test_threshold_candidates_reject_brief_gap_and_require_true_loss(outage_ms):
    kf = Filter_Create(outage_ms)
    kf.Kf6_GnssEpochTrack(Epoch_Create(1000000))
    kf.Kf6_GnssEpochTrack(Epoch_Create(1100000))
    assert not any(s.outage for s in kf._reacquire_groups)
    kf.Kf6_GnssEpochTrack(Epoch_Create(1100000 + outage_ms * 1000 + 1))
    assert all(s.outage for s in kf._reacquire_groups)
    for group in Kf6GnssGroup:
        kf.Kf6_GnssGroupResultProcess(group, Kf6UpdateResult.ACCEPTED)
    assert not any(s.outage for s in kf._reacquire_groups)
    assert kf.reacquire_count == 0


def test_old_rejection_gate_comparison_is_offline_only(tmp_path):
    results = []
    for legacy in (False, True):
        kf = Filter_Create()
        kf.outage_required = not legacy
        kf.state[3] = -30
        for step in range(64):
            epoch = Epoch_Create(1000000 + step * 40000)
            kf.Kf6_GnssEpochTrack(epoch)
            update = kf.Kf6_UpdateGnssVelocity(
                epoch.velocity_enu_mps, np.full(3, 0.04, dtype=np.float32), vertical_valid=True
            )
            kf.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.VELOCITY_HORIZONTAL, update.horizontal_result
            )
        results.append(
            {
                "legacy_gate": legacy,
                "inflation_counts": kf.inflation_counts,
                "final_velocity": kf.state[3:].tolist(),
            }
        )
    assert results[0]["inflation_counts"] == [0, 0, 0, 0]
    assert results[1]["inflation_counts"][2] >= 2
    (tmp_path / "continuous_rejection_comparison.json").write_text(json.dumps(results, indent=2))


def test_old_project_identity_and_new_integer_parameter_are_compatible():
    from dataclasses import replace

    from silverstar_flp.core.project import ReplayConfiguration_Validate
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin

    plugin = Kf6AlgorithmPlugin()
    additions = {"gnss_reacquire_outage_ms", "gnss_velocity_vertical_scale"}
    legacy = replace(
        plugin.metadata,
        parameter_schema=tuple(
            p for p in plugin.metadata.parameter_schema if p.parameter_id not in additions
        ),
    )
    configuration = {
        "algorithm_id": plugin.metadata.plugin_id,
        "algorithm_version": plugin.metadata.version,
        "mode": "recorded_configuration",
        "input_source": "corrected_imu",
        "actual_values": {p.parameter_id: p.default for p in legacy.parameter_schema},
        "parameter_schema_identity": legacy.ParameterSchemaIdentity_Get(),
        "provenance": "Firmware build configuration from .ssdecoder",
    }
    ReplayConfiguration_Validate(configuration)
    with pytest.raises(ValueError, match="schema_mismatch"):
        ReplayConfiguration_Validate({**configuration, "parameter_schema_identity": "f" * 64})
    with pytest.raises(ValueError, match="type_invalid"):
        plugin.metadata.Parameters_Validate({"gnss_reacquire_outage_ms": 300.5}, complete=False)
