"""Independent corrected-IMU frontend verification; never calibrates twice."""
from __future__ import annotations

import numpy as np

from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_BuildFromCorrectedImu,
    InertialIncrement_ReadRecorded,
    Mechanization_ConfigurationGet,
)


def Mechanization_Verify(dataset, start_us, end_us=None):
    config = Mechanization_ConfigurationGet(dataset)
    actual, diagnostics = InertialIncrement_BuildFromCorrectedImu(
        dataset.Records_Get('IMU_CORRECTED'), start_timestamp_us=start_us,
        end_timestamp_us=end_us, minimum_sample_rate_hz=config['minimum_sample_rate_hz'],
        maximum_sample_rate_hz=config['maximum_sample_rate_hz'])
    recorded = InertialIncrement_ReadRecorded(dataset.Records_Get('INERTIAL_INCREMENT'),
        start_timestamp_us=start_us, end_timestamp_us=end_us)
    by_end = {i.interval_end_timestamp_us: i for i in actual}
    rows = []
    first = None
    for expected in recorded:
        computed = by_end.pop(expected.interval_end_timestamp_us, None)
        row = {
            "sequence": expected.source_sequence,
            "timestamp_us": expected.interval_end_timestamp_us,
            "matched": computed is not None,
        }
        if computed is not None:
            row.update(
                source_sequence=computed.source_sequence,
                delta_theta_difference=(computed.delta_theta_b - expected.delta_theta_b).tolist(),
                delta_velocity_difference=(
                    computed.delta_velocity_b - expected.delta_velocity_b
                ).tolist(),
                dt_difference_s=float(computed.dt_s - expected.dt_s),
                start_timestamp_difference_us=computed.interval_start_timestamp_us
                - expected.interval_start_timestamp_us,
                end_timestamp_difference_us=computed.interval_end_timestamp_us
                - expected.interval_end_timestamp_us,
            )
            row["passed"] = bool(
                row["start_timestamp_difference_us"] == 0
                and abs(row["dt_difference_s"]) <= 2.0e-9
                and np.allclose(
                    computed.delta_theta_b, expected.delta_theta_b, rtol=2e-6, atol=1e-9
                )
                and np.allclose(
                    computed.delta_velocity_b, expected.delta_velocity_b, rtol=2e-6, atol=1e-8
                )
            )
        else:
            row['passed'] = False
        if not row['passed'] and first is None:
            first = row
        rows.append(row)
    return {'input': 'IMU_CORRECTED', 'calibration_applied': False,
            'recorded_count': len(recorded), 'computed_count': len(actual),
            'unmatched_computed_timestamps': sorted(by_end), 'intervals': rows,
            'first_divergence': first, 'invalid_sample_count': diagnostics.invalid_sample_count,
            'sample_gap_count': diagnostics.sample_gap_count,
            'passed': bool(rows) and first is None and not by_end}
