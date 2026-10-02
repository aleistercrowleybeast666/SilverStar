"""Audited body input conversion; navigation-frame inputs are never accepted."""

from __future__ import annotations

import numpy as np

from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep


def BodySteps_Build(dataset, bounds):
    exact = dataset.Records_Get("ESKF15_BODY_INPUT")
    steps, failure = [], None
    if exact:
        for record in exact:
            p = record.payload
            begin, end = (
                int(p[n]) for n in ("interval_start_timestamp_us", "interval_end_timestamp_us")
            )
            if begin < bounds.start_timestamp_us or end > bounds.end_timestamp_us:
                continue
            if abs(float(p["dt_s"]) - (end - begin) * 1e-6) > 2e-6:
                failure = {"timestamp_us": end, "reason": "eskf15_body_input_quality_or_dt"}
                break
            gyro, accel = np.asarray(p["body_gyro_radps"]), np.asarray(p["body_accel_mps2"])
            steps.append(
                BodyStep(
                    begin,
                    end,
                    gyro[:3],
                    accel[:3],
                    gyro[3:],
                    accel[3:],
                    int(p["source_id"]),
                    int(p["calibration_generation"]),
                    int(p["quality_flags"]),
                )
            )
        return steps, failure, True
    from silverstar_flp.plugins.algorithms.pure_ins.mechanization import Mechanization_ConfigurationGet
    if Mechanization_ConfigurationGet(dataset)["subsample_count"] != 2:
        return [], {"timestamp_us": bounds.start_timestamp_us,
                    "reason": "unsupported_mechanization_aggregation"}, False
    records = [
        r
        for r in dataset.Records_Get("IMU_CORRECTED")
        if bounds.start_timestamp_us
        <= int(r.payload["sample_timestamp_us"])
        <= bounds.end_timestamp_us
    ]
    for index in range(2, len(records), 2):
        samples = [r.payload for r in records[index - 2 : index + 1]]
        times = [int(p["sample_timestamp_us"]) for p in samples]
        source = [int(p.get("source_id", 0)) for p in samples]
        generation = [int(p.get("calibration_generation", 0)) for p in samples]
        if (
            any(
                int(p.get("valid_mask", 0)) & 3 != 3 or not p.get("correction_valid")
                for p in samples
            )
            or len(set(source)) != 1
            or len(set(generation)) != 1
        ):
            failure = {"timestamp_us": times[-1], "reason": "eskf15_invalid_body_input"}
            break
        if any(not 0 < delta <= 13_500 for delta in np.diff(times)):
            failure = {"timestamp_us": times[-1], "reason": "eskf15_body_gap"}
            break
        a, b, c = samples

        def mean(name, first, last):
            return 0.5 * (np.asarray(first[name]) + np.asarray(last[name]))

        steps.append(
            BodyStep(
                times[0],
                times[2],
                mean("gyro_b_radps", a, b),
                mean("accel_b_mps2", a, b),
                mean("gyro_b_radps", b, c),
                mean("accel_b_mps2", b, c),
                source[0],
                generation[0],
            )
        )
    return steps, failure, False
