"""Trusted interpretation of the separate horizon v1 wire records.

Structural validation keeps honest fault/incomplete logs inspectable. Numerical
admission additionally requires paired operations and the relevant status. This
module does not infer a decoder identity or activate a Recorded algorithm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from silverstar_flp.decoder_profiles.contract_data import Contract_Load
from silverstar_flp.decoder_profiles.errors import DecoderProfileError

CONTRACT = Contract_Load("navigation_fusion_horizon_records_v1.json")
RECORDS = {row["name"]: row for row in CONTRACT["records"]}
MEASUREMENT = "FUSION_HORIZON_MEASUREMENT"
STATUS = "FUSION_HORIZON_STATUS"
_ALGORITHMS = {1: (2, 1, 512), 2: (1, 2, 832)}
_SIZES = {"u8": 1, "u16": 2, "u32": 4, "u64": 8, "f32": 4}
_IMMUTABLE = (
    "sample_timestamp_us",
    "receive_timestamp_us",
    "measurement_timestamp_us",
    "operation_sequence",
    "epoch",
    "source_id",
    "calibration_generation",
    "source_sequence",
    "algorithm_id",
    "algorithm_revision",
    "numerical_revision",
    "group",
    "physically_valid",
    "observation",
    "prepared_variance",
    "quality_scale",
    "consistency_scale",
    "kf_availability_timestamp_us",
    "kf_consistency_start_timestamp_us",
    "kf_recovery_generation",
    "kf_consistent_count",
    "kf_outage",
    "kf_loss_latched",
    "kf_recovery_valid",
    "kf_consistency_valid",
)


def _Invalid(reason):
    raise DecoderProfileError("fusion_horizon_" + reason)


def _Unsigned(payload, key, bits=64):
    value = payload.get(key)
    if type(value) is not int or not 0 <= value < 1 << bits:
        _Invalid("field_invalid:" + key)
    return value


def _Finite(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and abs(value) <= 3.4028234663852886e38
    )


def _Equal(first, second):
    # Decoder vectors can be immutable tuples or lists. NaNs are allowed only
    # in rejected external-input records, which never have a completion pair.
    if isinstance(first, (tuple, list)) and isinstance(second, (tuple, list)):
        return len(first) == len(second) and all(
            _Equal(a, b) for a, b in zip(first, second, strict=True)
        )
    return first == second


def FusionHorizonLayout_Validate(layout):
    row = RECORDS.get(layout.name)
    if row is None or (layout.record_type, layout.record_version, layout.payload_size) != (
        int(row["id"], 0),
        row["version"],
        row["payload_size"],
    ):
        _Invalid("layout_identity_invalid")
    if len(layout.fields) != len(row["fields"]):
        _Invalid("layout_fields_invalid")
    size = 0
    for actual, expected in zip(layout.fields, row["fields"], strict=True):
        count = expected.get("count", 1)
        if (
            (actual.name, actual.data_type, actual.count)
            != (expected["name"], expected["type"], count)
            or actual.scale != 1
            or actual.offset != 0
        ):
            _Invalid("layout_field_invalid:" + expected["name"])
        size += _SIZES[expected["type"]] * count
    if size != row["payload_size"]:
        _Invalid("layout_size_invalid")


def _Record_Validate(record, algorithm_id):
    row = RECORDS[record.record_name]
    if (record.record_type, record.record_version, record.payload_length) != (
        int(row["id"], 0),
        row["version"],
        row["payload_size"],
    ):
        _Invalid("record_identity_invalid")
    p = record.payload
    if type(record.timestamp_us) is not int or not 0 <= record.timestamp_us < 1 << 64:
        _Invalid("header_timestamp_invalid")
    for field in row["fields"]:
        kind = field["type"]
        if kind != "f32":
            _Unsigned(p, field["name"], _SIZES[kind] * 8)
        elif field.get("count", 1) > 1:
            vector = p.get(field["name"])
            if (
                not isinstance(vector, (tuple, list))
                or len(vector) != field["count"]
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in vector)
            ):
                _Invalid("vector_invalid:" + field["name"])
        elif isinstance(p.get(field["name"]), bool) or not isinstance(
            p.get(field["name"]), (int, float)
        ):
            _Invalid("field_invalid:" + field["name"])
    actual = _Unsigned(p, "algorithm_id", 8)
    if actual not in _ALGORITHMS or algorithm_id is not None and actual != algorithm_id:
        _Invalid("algorithm_identity_invalid")
    if (p["algorithm_revision"], p["numerical_revision"]) != _ALGORITHMS[actual][:2] or p[
        "fusion_timing_mode"
    ] != 2:
        _Invalid("revision_or_mode_invalid")
    return p


def _Measurement_Validate(record, algorithm_id):
    p = _Record_Validate(record, algorithm_id)
    if (
        any(
            p[key] not in (0, 1)
            for key in ("phase", "physically_valid", "admitted", "effective_update")
        )
        or p["group"] > 4
    ):
        _Invalid("measurement_flags_invalid")
    kf_flags = ("kf_outage", "kf_loss_latched", "kf_recovery_valid", "kf_consistency_valid")
    kf_fields = (
        *kf_flags,
        "kf_availability_timestamp_us",
        "kf_consistency_start_timestamp_us",
        "kf_recovery_generation",
        "kf_consistent_count",
    )
    if any(p[key] not in (0, 1) for key in kf_flags):
        _Invalid("kf_certificate_flags_invalid")
    if (p["algorithm_id"] == 2 or p["group"] == 4) and any(p[key] != 0 for key in kf_fields):
        _Invalid("kf_certificate_namespace_invalid")
    if (
        record.timestamp_us != p["evaluation_timestamp_us"]
        or p["execution_result"] not in CONTRACT["execution_results"].values()
    ):
        _Invalid("measurement_execution_invalid")
    flags = p["timing_flags"]
    if flags & ~15 or flags & 12 == 12 or (not flags & 1 and p["measurement_timestamp_us"] != 0):
        _Invalid("measurement_timing_flags_invalid")
    if p["phase"] == 0:
        if (
            p["admitted"] != 0
            or p["effective_update"] != 0
            or p["application_timestamp_us"] != 0
            or p["update_result"] != 255
            or p["nis"] != -1
            or flags & 2
        ):
            _Invalid("request_publication_invalid")
        if p["execution_result"] != CONTRACT["execution_results"]["queued"]:
            return p
    elif (
        p["admitted"] != 1
        or p["execution_result"] != 0
        or p["physically_valid"] != 1
        or p["application_timestamp_us"] != p["measurement_timestamp_us"]
        or flags & 3 != 3
        or p["update_result"] not in (0, 1, 2, 3)
        or not _Finite(p["nis"])
        or p["nis"] < 0
        or p["effective_update"]
        and p["update_result"] not in (0, 1)
    ):
        _Invalid("completion_publication_invalid")
    if (
        p["physically_valid"] != 1
        or flags & 1 != 1
        or flags & 12 not in (4, 8)
        or not 0
        < p["measurement_timestamp_us"]
        <= p["receive_timestamp_us"]
        <= p["evaluation_timestamp_us"]
        or p["group"] == 4
        and p["source_id"] != 1
        or p["group"] < 4
        and p["source_id"] >= 4
    ):
        _Invalid("admitted_request_invalid")
    # Age admission applies at receipt, not at the later completion publication.
    if p["phase"] == 0 and (
        p["evaluation_timestamp_us"] - p["measurement_timestamp_us"] > 600000
        or p["evaluation_timestamp_us"] - p["receive_timestamp_us"] > 500000
    ):
        _Invalid("request_age_invalid")
    dimension = 2 if p["group"] in (0, 2) else 1
    for key in ("quality_scale", "consistency_scale", "robust_scale"):
        if not _Finite(p[key]) or p[key] < 1:
            _Invalid("measurement_scale_invalid")
    for index in range(dimension):
        if (
            not _Finite(p["observation"][index])
            or not _Finite(p["prepared_variance"][index])
            or p["prepared_variance"][index] < 1.401298464324817e-45
        ):
            _Invalid("measurement_value_invalid")
        if p["phase"] and (
            not _Finite(p["innovation"][index])
            or not _Finite(p["effective_variance"][index])
            or p["effective_variance"][index] <= 0
        ):
            _Invalid("completion_value_invalid")
    return p


def _Status_Validate(record, algorithm_id, horizon_us):
    p = _Record_Validate(record, algorithm_id)
    if (
        p["reserved_count"] != 0
        or p["horizon_initialized"] not in (0, 1)
        or p["failure_operation_valid"] not in (0, 1)
        or p["phase"] not in (0, 1, 2)
        or p["execution_result"] not in CONTRACT["execution_results"].values()
        or p["output_state_timestamp_us"] != p["output_covariance_timestamp_us"]
    ):
        _Invalid("status_invalid")
    if not p["horizon_initialized"]:
        if p["phase"] != 2 or p["input_present_timestamp_us"] or p["primary_timestamp_us"]:
            _Invalid("uninitialized_status_invalid")
    elif (
        not 10000 <= p["horizon_us"] <= 550000
        or horizon_us is not None
        and p["horizon_us"] != horizon_us
    ):
        _Invalid("horizon_parameter_mismatch")
    if p["phase"] != 2:
        if (
            not p["primary_timestamp_us"]
            <= p["output_state_timestamp_us"]
            == p["input_present_timestamp_us"]
            == record.timestamp_us
            or p["body_count"] > 160
            or p["event_count"] > 64
            or p["completion_count"] > 64
            or p["work_count"] > p["maximum_work"]
            or p["maximum_work"] > _ALGORITHMS[p["algorithm_id"]][2]
            or p["failure_operation_valid"]
        ):
            _Invalid("active_status_invalid")
        expected = 12 if p["phase"] == 0 else 0
        if p["execution_result"] != expected:
            _Invalid("status_phase_invalid")
    return p


@dataclass(frozen=True, slots=True)
class FusionHorizonEvidence:
    requests: tuple
    completions: tuple
    statuses: tuple
    pending: tuple
    replay_blockers: tuple[str, ...]


def FusionHorizonRecords_Validate(dataset, *, algorithm_id=None, horizon_us=None):
    """Validate wire semantics without changing records or inventing defaults.

    Missing completion evidence and honest fault statuses are numerical replay
    blockers, not reasons to discard the original recorded bytes.
    """
    if algorithm_id is not None and (
        type(algorithm_id) is not int or algorithm_id not in _ALGORITHMS
    ):
        _Invalid("expected_algorithm_invalid")
    if horizon_us is not None and (
        type(horizon_us) is not int or not 10000 <= horizon_us <= 550000
    ):
        _Invalid("expected_horizon_invalid")
    records = sorted(
        (r for name in RECORDS for r in dataset.Records_Get(name)), key=lambda r: r.file_offset
    )
    requests, completions, statuses, pending = [], [], [], {}
    seen, last_operation, blockers, last_status = set(), {}, [], {}
    for record in records:
        if record.record_name == STATUS:
            p = _Status_Validate(record, algorithm_id, horizon_us)
            epoch = (p["algorithm_id"], p["epoch"], p["calibration_generation"])
            statuses.append(record)
            last_status[epoch] = record
            if p["phase"] == 2:
                blockers.append("fusion_horizon_fault_recorded")
            continue
        p = _Measurement_Validate(record, algorithm_id)
        epoch = (p["algorithm_id"], p["epoch"], p["calibration_generation"])
        key = (*epoch, p["operation_sequence"])
        if p["phase"] == 0:
            # KF operation IDs also belong to ESTIMATOR_STEP body admissions.
            # A gap alone cannot prove a missing measurement; retain strict
            # forward order and pair ownership. Complete-log/algorithm replay
            # admission must separately verify body records and loss evidence.
            if (
                key in seen
                or epoch in last_operation
                and not 0
                < ((p["operation_sequence"] - last_operation[epoch]) & 0xFFFFFFFF)
                < 0x80000000
            ):
                _Invalid("operation_discontinuity")
            seen.add(key)
            last_operation[epoch] = p["operation_sequence"]
            requests.append(record)
            if p["execution_result"] == 11:
                pending[key] = record
        else:
            request = pending.pop(key, None)
            if request is None:
                _Invalid("completion_request_missing_or_duplicate")
            if (
                any(not _Equal(request.payload[key], p[key]) for key in _IMMUTABLE)
                or p["timing_flags"] != request.payload["timing_flags"] | 2
                or p["evaluation_timestamp_us"] < request.payload["evaluation_timestamp_us"]
            ):
                _Invalid("completion_request_mismatch")
            completions.append(record)
    if not statuses:
        blockers.append("fusion_horizon_status_missing")
    for request in pending.values():
        p = request.payload
        epoch = (p["algorithm_id"], p["epoch"], p["calibration_generation"])
        final = last_status.get(epoch)
        if final is None or final.payload["primary_timestamp_us"] >= p["measurement_timestamp_us"]:
            blockers.append("fusion_horizon_completion_missing")
    # A second legacy record stream cannot establish which operation ran.
    if any(
        dataset.Records_Get(name)
        for name in ("GNSS_MEASUREMENT", "BARO_MEASUREMENT", "ESKF15_MEASUREMENT")
    ):
        blockers.append("fusion_horizon_legacy_measurement_stream_present")
    return FusionHorizonEvidence(
        tuple(requests),
        tuple(completions),
        tuple(statuses),
        tuple(pending.values()),
        tuple(dict.fromkeys(blockers)),
    )
