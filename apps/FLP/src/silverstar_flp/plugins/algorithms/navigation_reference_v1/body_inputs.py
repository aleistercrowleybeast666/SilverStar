"""Explicit body samples for the three augmented host models only.

Current IMU_CORRECTED record version 0 does not record quality or calibration generation. Missing
evidence can be supplied only as a declared What-if assumption by the caller.
Legacy odd-duration ESKF15_BODY_INPUT means used a floored half boundary.
"""
from __future__ import annotations

import numpy as np

from silverstar_flp.plugins.algorithms.eskf15.inputs import BodySteps_Build as LegacyBodySteps_Build
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import Mechanization_ConfigurationGet


def Assumption_Validate(assumption):
    if assumption is None:
        return
    if (not isinstance(assumption, dict) or set(assumption) != {
            "provenance", "quality_flags", "calibration_generation"}
            or assumption["provenance"] != "user_configuration"
            or type(assumption["quality_flags"]) is not int
            or assumption["quality_flags"] != 0
            or type(assumption["calibration_generation"]) is not int
            or not 0 <= assumption["calibration_generation"] < 2**32):
        raise ValueError("navigation_body_input_assumption_fields")


def _Integer_Get(payload, name, bits=32):
    value = payload[name]
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= value < 2**bits:
        raise ValueError("navigation_body_integer:" + name)
    return int(value)


def _Vector_Get(payload, name):
    value = np.asarray(payload[name], dtype=np.float64)
    if value.shape != (3,) or not np.isfinite(value).all() or np.max(np.abs(value)) > np.finfo(np.float32).max:
        raise ValueError("navigation_body_vector:" + name)
    # Recorded corrected vectors and C producer operands are binary32.
    return value.astype(np.float32)


def BodySourceEnd_Get(dataset):
    records = dataset.Records_Get("ESKF15_BODY_INPUT")
    field = "interval_end_timestamp_us"
    if not records:
        records = dataset.Records_Get("IMU_CORRECTED")
        field = "sample_timestamp_us"
    return max((_Integer_Get(record.payload, field, 64) for record in records), default=None)


def _Evidence_Get(payload, name, assumption):
    if name in payload:
        return _Integer_Get(payload, name)
    if assumption is None:
        raise ValueError("navigation_body_evidence_missing:" + name)
    return assumption[name]


def _Means_Build(times, vectors):
    if len(times) == 2:
        a, b = vectors
        # Match the endpoint producer's separate binary32 arithmetic operations.
        with np.errstate(over="ignore", invalid="ignore"):
            return ((np.float32(3) * a + b) * np.float32(.25),
                    (a + np.float32(3) * b) * np.float32(.25))
    # Relative microseconds are exact over the admitted 20 ms domain, including
    # half-microseconds. Never convert an absolute uint64 sample clock to float.
    relative = [0, times[1] - times[0], times[2] - times[0]]
    midpoint = relative[-1] / 2.0
    values = [value.astype(np.float64) for value in vectors]
    means = []
    for begin, end in ((0.0, midpoint), (midpoint, float(relative[-1]))):
        integral = np.zeros(3)
        for index in range(2):
            left, right = max(begin, relative[index]), min(end, relative[index + 1])
            if right > left:
                span = relative[index + 1] - relative[index]
                fraction = ((left - relative[index]) + (right - relative[index])) / span
                mean = values[index] + .5 * fraction * (values[index + 1] - values[index])
                integral += mean * (right - left)
        means.append((integral / (end - begin)).astype(np.float32))
    return means


def _Corrected_Build(dataset, bounds, assumption):
    recorded = dataset.RecordAtOrBefore_Get("SYSTEM_CONFIG", bounds.start_timestamp_us)
    if recorded is None or "mechanization_subsample_count" not in recorded.payload:
        raise ValueError("navigation_recorded_aggregation_missing")
    aggregation = Mechanization_ConfigurationGet(dataset)["subsample_count"]
    if aggregation not in (1, 2):
        raise ValueError("unsupported_mechanization_aggregation")
    records = [record for record in dataset.Records_Get("IMU_CORRECTED")
               if bounds.start_timestamp_us <= _Integer_Get(record.payload, "sample_timestamp_us", 64)
               <= bounds.end_timestamp_us]
    steps = []
    for index in range(aggregation, len(records), aggregation):
        samples = [record.payload for record in records[index - aggregation:index + 1]]
        times = [_Integer_Get(sample, "sample_timestamp_us", 64) for sample in samples]
        if (not 0 < times[-1] - times[0] <= 20000
                or any(last <= first for first, last in zip(times, times[1:]))):
            raise ValueError("navigation_body_interval_domain")
        source = [_Integer_Get(sample, "source_id", 16) for sample in samples]
        generation = [_Evidence_Get(sample, "calibration_generation", assumption) for sample in samples]
        quality = [_Evidence_Get(sample, "quality_flags", assumption) for sample in samples]
        if any(value != 0 for value in quality):
            raise ValueError("navigation_body_quality_policy_unsupported")
        if (len(set(source)) != 1 or len(set(generation)) != 1
                or any(_Integer_Get(sample, "valid_mask") & 3 != 3
                       or sample["correction_valid"] != 1 for sample in samples)):
            raise ValueError("navigation_invalid_body_identity_or_validity")
        gyro = _Means_Build(times, [_Vector_Get(sample, "gyro_b_radps") for sample in samples])
        accel = _Means_Build(times, [_Vector_Get(sample, "accel_b_mps2") for sample in samples])
        if not all(np.isfinite(vector).all() for vector in (*gyro, *accel)):
            raise ValueError("navigation_body_mean_nonfinite")
        steps.append(BodyStep(times[0], times[-1], gyro[0], accel[0], gyro[1], accel[1],
                              source[0], generation[0], 0))
    return steps


def BodySteps_Build(dataset, bounds, assumption=None):
    Assumption_Validate(assumption)
    exact = bool(dataset.Records_Get("ESKF15_BODY_INPUT"))
    try:
        if exact:
            # Keep the established even-interval record/initial-snapshot contract.
            for record in dataset.Records_Get("ESKF15_BODY_INPUT"):
                payload = record.payload
                begin = _Integer_Get(payload, "interval_start_timestamp_us", 64)
                end = _Integer_Get(payload, "interval_end_timestamp_us", 64)
                if begin < bounds.start_timestamp_us or end > bounds.end_timestamp_us:
                    continue
                if (end - begin) % 2:
                    raise ValueError("navigation_legacy_odd_body_half_semantics_unproven")
                if not np.isfinite(payload["dt_s"]):
                    raise ValueError("navigation_body_dt_nonfinite")
            return LegacyBodySteps_Build(dataset, bounds)
        return _Corrected_Build(dataset, bounds, assumption), None, False
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        return [], {"timestamp_us": bounds.start_timestamp_us, "reason": str(exc)}, exact
