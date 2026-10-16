"""Own immutable numerical inputs from the separate validated horizon records.

Callers still establish the exact decoder, mission/body identity and replay
schedule. These conversions never infer a source time, variance or certificate.
"""

from collections.abc import Mapping
from dataclasses import replace

import numpy as np

from silverstar_flp.decoder_profiles.fusion_horizon_records import _Measurement_Validate
from silverstar_flp.plugins.algorithms.eskf15.horizon import HorizonMeasurement
from silverstar_flp.plugins.algorithms.kf6.horizon import KfHorizonEvent, KfHorizonEvidence


def _Request_Get(record, algorithm_id, epoch, calibration_generation):
    p = _Measurement_Validate(record, algorithm_id)
    if (
        type(epoch) is not int
        or type(calibration_generation) is not int
        or p["phase"] != 0
        or p["epoch"] != epoch
        or p["calibration_generation"] != calibration_generation
    ):
        raise ValueError("fusion_horizon_request_identity_mismatch")
    return p


def KfHorizonEvent_FromRecord(record, *, epoch, calibration_generation):
    p = _Request_Get(record, 1, epoch, calibration_generation)
    evidence = KfHorizonEvidence(
        p["kf_availability_timestamp_us"],
        p["kf_consistency_start_timestamp_us"],
        p["kf_recovery_generation"],
        p["kf_consistent_count"],
        p["kf_outage"],
        p["kf_loss_latched"],
        p["kf_recovery_valid"],
        p["kf_consistency_valid"],
    )
    return KfHorizonEvent(
        p["measurement_timestamp_us"],
        p["receive_timestamp_us"],
        p["source_sequence"],
        p["operation_sequence"],
        p["epoch"],
        p["source_id"],
        p["calibration_generation"],
        p["group"],
        np.asarray(p["observation"], dtype=np.float32).copy(),
        np.asarray(p["prepared_variance"], dtype=np.float32).copy(),
        p["physically_valid"],
        evidence,
    )


def EskfHorizonEvent_FromRecord(record, *, epoch, calibration_generation):
    p = _Request_Get(record, 2, epoch, calibration_generation)
    dimension = 2 if p["group"] in (0, 2) else 1
    prepared = np.asarray(p["prepared_variance"][:dimension], dtype=np.float32).astype(float)
    return HorizonMeasurement(
        (p["operation_sequence"], p["group"]),
        p["measurement_timestamp_us"],
        p["receive_timestamp_us"],
        p["group"],
        np.asarray(p["observation"][:dimension], dtype=np.float32).astype(float),
        prepared.copy(),
        bool(p["physically_valid"]),
        p["quality_scale"],
        p["consistency_scale"],
        p["source_id"],
        p["calibration_generation"],
        p["source_sequence"],
        p["epoch"],
        prepared,
    )


def HorizonWhatIfDelays_Validate(requests, changed_delays_ms):
    """Copy explicit changed groups; missing timestamp trust is never guessed."""
    if not isinstance(changed_delays_ms, Mapping):
        raise ValueError("fusion_horizon_what_if_delay_invalid")
    copied = dict(changed_delays_ms)
    if any(
        type(group) is not int
        or not 0 <= group <= 4
        or type(value) is not int
        or not 0 <= value <= 0xFFFFFFFF
        for group, value in copied.items()
    ):
        raise ValueError("fusion_horizon_what_if_delay_invalid")
    if any(
        record.payload["group"] in copied and record.payload["timing_flags"] & 12 not in (4, 8)
        for record in requests
    ):
        raise ValueError("fusion_horizon_delay_trust_evidence_missing")
    return copied


def HorizonWhatIfTime_Apply(record, event, changed_delays_ms):
    if event.group not in changed_delays_ms or record.payload["timing_flags"] & 4:
        return event
    delay_us = changed_delays_ms[event.group] * 1000
    source_us = event.receive_us - delay_us if event.receive_us >= delay_us else 0
    return replace(event, timestamp_us=source_us)
