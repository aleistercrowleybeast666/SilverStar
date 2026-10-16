"""Trusted timing validation against the repository's data-only wire contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from silverstar_flp.decoder_profiles.contract_data import Contract_Load
from silverstar_flp.decoder_profiles.errors import DecoderProfileError

CONTRACT = Contract_Load("navigation_fusion_timing_records_v2.json")
RECORDS = {row["name"]: row for row in CONTRACT["records"]}
FusionExecutionResult = IntEnum("FusionExecutionResult", CONTRACT["execution_results"])
SOURCE_RESOLVED = CONTRACT["timing_flags"]["SOURCE_RESOLVED"]
APPLICATION_EPOCH_VALID = CONTRACT["timing_flags"]["APPLICATION_EPOCH_VALID"]
TRUSTED_SOURCE = CONTRACT["timing_flags"]["TRUSTED_SOURCE"]
DELAY_FALLBACK = CONTRACT["timing_flags"]["DELAY_FALLBACK"]
LEGACY_PRESENT_OVERRIDE = CONTRACT["timing_flags"]["LEGACY_PRESENT_OVERRIDE"]


@dataclass(frozen=True, slots=True)
class FusionSourceIdentity:
    source_namespace: str
    source_id: int
    mission_epoch: int
    calibration_generation: int
    source_sequence: int
    group: int


@dataclass(frozen=True, slots=True)
class FusionTimingOperation:
    identity: FusionSourceIdentity
    mode: int
    source_us: int | None
    receive_us: int
    application_us: int | None
    present_us: int
    execution_result: FusionExecutionResult
    flags: int


def _Invalid(reason):
    raise DecoderProfileError("fusion_timing_" + reason)


def _Unsigned_Get(payload, key, bits=64):
    value = payload.get(key)
    if type(value) is not int or not 0 <= value < (1 << bits):
        _Invalid("record_field_invalid:" + key)
    return value


def FusionTimingLayout_Validate(layout):
    definition = RECORDS.get(layout.name)
    if definition is None or (layout.record_type, layout.record_version, layout.payload_size) != (
        definition["record_id"],
        2,
        definition["payload_size"],
    ):
        _Invalid("record_layout_identity_invalid")
    expected = definition["v1_fields"] + definition["appended_fields"]
    if len(layout.fields) != len(expected):
        _Invalid("record_layout_fields_invalid")
    offset = 0
    for field, row in zip(layout.fields, expected, strict=True):
        if (
            (field.name, field.data_type, field.count, offset)
            != (row["name"], row["type"], row["count"], row["offset"])
            or field.scale != 1
            or field.offset != 0
        ):
            _Invalid("record_layout_field_invalid:" + row["name"])
        offset += field.byte_size
    if offset != definition["payload_size"]:
        _Invalid("record_layout_size_invalid")


def FusionTimingCatalog_Validate(catalog, identity):
    if identity is None or identity.evidence != "explicit_declaration":
        return
    for layout in catalog.layouts.values():
        if layout.name in RECORDS and layout.record_version == 2:
            FusionTimingLayout_Validate(layout)
    if identity.mode == 2:
        from silverstar_flp.decoder_profiles.fusion_horizon_records import (
            RECORDS as HORIZON_RECORDS,
        )
        from silverstar_flp.decoder_profiles.fusion_horizon_records import (
            FusionHorizonLayout_Validate,
        )

        for row in HORIZON_RECORDS.values():
            layout = catalog.layouts.get((int(row["id"], 0), row["version"]))
            if layout is None:
                _Invalid("horizon_record_layout_missing:" + row["name"])
            FusionHorizonLayout_Validate(layout)
        return
    from silverstar_flp.decoder_profiles.fusion_timing import FusionTimingVersionKnown_Is

    if not FusionTimingVersionKnown_Is(identity) or identity.unavailable_reason:
        return
    required = (
        ("ESKF15_MEASUREMENT",)
        if identity.component.endswith("eskf15")
        else ("GNSS_MEASUREMENT", "BARO_MEASUREMENT")
    )
    for name in required:
        definition = RECORDS[name]
        layout = catalog.layouts.get((definition["record_id"], 2))
        if layout is None:
            _Invalid("record_layout_missing:" + name)
        FusionTimingLayout_Validate(layout)


def _Operation_Get(record, group, mode):
    p = record.payload
    gnss = record.record_name == "GNSS_MEASUREMENT"
    eskf = record.record_name == "ESKF15_MEASUREMENT"
    prefix = ("position_" if group < 2 else "velocity_") if gnss else ""
    source_key = "measurement_timestamp_us" if eskf else prefix + "source_timestamp_us"
    source = _Unsigned_Get(p, source_key)
    receive = _Unsigned_Get(p, "receive_timestamp_us")
    present = _Unsigned_Get(
        p, "evaluation_timestamp_us" if eskf else "estimator_present_timestamp_us"
    )
    application = _Unsigned_Get(p, prefix + "application_timestamp_us")
    flags = _Unsigned_Get(p, prefix + "timing_flags", 8)
    execution = _Unsigned_Get(p, prefix + "execution_result", 8)
    if (
        flags & CONTRACT["timing_flags_reserved_mask"]
        or flags & TRUSTED_SOURCE
        and flags & DELAY_FALLBACK
    ):
        _Invalid("record_flags_invalid")
    if execution not in CONTRACT["execution_results"].values() or (
        mode == 0 and execution not in CONTRACT["current_execution_values"]
    ):
        _Invalid("record_execution_invalid")
    if not flags & SOURCE_RESOLVED and source != 0:
        _Invalid("record_source_evidence_invalid")
    if flags & SOURCE_RESOLVED and source == 0:
        _Invalid("record_source_evidence_invalid")
    if not flags & APPLICATION_EPOCH_VALID and application != 0:
        _Invalid("record_application_evidence_invalid")
    if flags & APPLICATION_EPOCH_VALID and (
        application == 0 or (mode == 0 and application != present)
    ):
        _Invalid("record_application_evidence_invalid")
    if flags & LEGACY_PRESENT_OVERRIDE and (
        mode != 1
        or eskf
        or flags & TRUSTED_SOURCE
        or not flags & DELAY_FALLBACK
        or (flags & APPLICATION_EPOCH_VALID and application != present)
        or (flags & SOURCE_RESOLVED and source != receive)
    ):
        _Invalid("record_legacy_override_invalid")
    if mode == 0 and execution == FusionExecutionResult.COMPLETE:
        if flags & (SOURCE_RESOLVED | APPLICATION_EPOCH_VALID) != (
            SOURCE_RESOLVED | APPLICATION_EPOCH_VALID
        ):
            _Invalid("record_complete_evidence_missing")
        if not 0 < source <= receive <= present or (
            present - source > CONTRACT["current_max_source_age_us"]
            or present - receive > CONTRACT["current_max_receive_age_us"]
        ):
            _Invalid("record_complete_admission_inconsistent")
    if not eskf and mode == 0 and _Unsigned_Get(p, prefix + "replay_result", 8) != 255:
        _Invalid("record_replay_sentinel_invalid")
    source_id = _Unsigned_Get(p, "source_id", 32)
    baro = group == 4
    if baro and (mode == 0 or not eskf) and source_id != 1:
        _Invalid("record_barometer_namespace_invalid")
    namespace = (
        ("legacy_eskf_imu_alias" if eskf and mode == 1 else "estimator_barometer_producer")
        if baro
        else "gnss_instance"
    )
    identity = FusionSourceIdentity(
        namespace,
        source_id,
        _Unsigned_Get(p, "epoch" if eskf else "replay_epoch", 32),
        _Unsigned_Get(p, "calibration_generation", 32),
        _Unsigned_Get(p, "source_sequence" if eskf else "sequence", 32),
        group,
    )
    return FusionTimingOperation(
        identity,
        mode,
        source if flags & SOURCE_RESOLVED else None,
        receive,
        application if flags & APPLICATION_EPOCH_VALID else None,
        present,
        FusionExecutionResult(execution),
        flags,
    )


def FusionTimingOperations_Get(record, *, declared_mode):
    definition = RECORDS.get(record.record_name)
    if definition is None or (record.record_type, record.record_version, record.payload_length) != (
        definition["record_id"],
        2,
        definition["payload_size"],
    ):
        _Invalid("record_identity_invalid")
    mode = _Unsigned_Get(record.payload, "fusion_timing_mode", 8)
    if type(declared_mode) is not int or mode not in (0, 1) or mode != declared_mode:
        _Invalid("record_mode_mismatch")
    reserved = record.payload.get("timing_reserved")
    values = reserved if isinstance(reserved, (tuple, list)) else (reserved,)
    count = 3 if record.record_name == "GNSS_MEASUREMENT" else 1
    if len(values) != count or any(type(v) is not int or v != 0 for v in values):
        _Invalid("record_reserved_invalid")
    if record.record_name == "GNSS_MEASUREMENT":
        groups = range(4)
    elif record.record_name == "BARO_MEASUREMENT":
        groups = (4,)
    else:
        group = _Unsigned_Get(record.payload, "group", 8)
        if group > 4:
            _Invalid("record_group_invalid")
        groups = (group,)
    return tuple(_Operation_Get(record, group, mode) for group in groups)


def FusionTimingRecords_Validate(dataset):
    from silverstar_flp.decoder_profiles.fusion_timing import FusionTiming_FromSemantics

    context = getattr(dataset, "semantic_context", None)
    identity = FusionTiming_FromSemantics(getattr(context, "raw_metadata", {}))
    for name in RECORDS:
        for record in dataset.Records_Get(name):
            if record.record_version == 2:
                if (
                    identity is None
                    or identity.mode is None
                    or identity.evidence != "explicit_declaration"
                ):
                    _Invalid("record_declaration_missing")
                FusionTimingOperations_Get(record, declared_mode=identity.mode)


def FusionTimingCurrentPackets_Validate(dataset):
    """Numerical admission only: raw truncated/fault logs remain readable.

    The ESKF backend emits all four GNSS groups consecutively. These records
    prove the packet receipt boundary; record_sequence is never a producer ID.
    """
    records = dataset.Records_Get("ESKF15_MEASUREMENT")
    identity_fields = (
        "source_id",
        "source_sequence",
        "epoch",
        "calibration_generation",
        "receive_timestamp_us",
        "evaluation_timestamp_us",
    )
    previous = None
    for record in records:
        p = record.payload
        epoch = (p["epoch"], p["calibration_generation"])
        if (
            previous is not None
            and epoch == previous[0]
            and ((p["operation_sequence"] - previous[1]) & 0xFFFFFFFF) != 1
        ):
            _Invalid("current_packet_operation_discontinuity")
        previous = (epoch, p["operation_sequence"])
    index = 0
    while index < len(records):
        first = records[index].payload
        if first["group"] == 4:
            index += 1
            continue
        packet = records[index : index + 4]
        if len(packet) != 4 or [r.payload["group"] for r in packet] != [0, 1, 2, 3]:
            _Invalid("current_packet_groups_incomplete_or_reordered")
        for offset, record in enumerate(packet):
            p = record.payload
            if (
                any(p[key] != first[key] for key in identity_fields)
                or (p["operation_sequence"] - first["operation_sequence"]) & 0xFFFFFFFF != offset
            ):
                _Invalid("current_packet_identity_inconsistent")
        index += 4


def CurrentAdmission_Get(source_us, receive_us, present_us, epoch_start_us=0):
    if not 0 < source_us <= receive_us <= present_us:
        return FusionExecutionResult.INVALID
    if source_us < epoch_start_us or receive_us < epoch_start_us:
        return FusionExecutionResult.EPOCH_MISMATCH
    if (
        present_us - source_us > CONTRACT["current_max_source_age_us"]
        or present_us - receive_us > CONTRACT["current_max_receive_age_us"]
    ):
        return FusionExecutionResult.STALE
    return FusionExecutionResult.COMPLETE


class FusionSequenceTracker:
    """Bounded producer watermarks, never retained observations or state history."""

    def __init__(self):
        self._watermarks = {}

    def Check(self, namespace, source, sequence, mask):
        if (
            type(source) is not int
            or not 0 <= source <= (3 if namespace == "gnss" else 1)
            or type(sequence) is not int
            or not 0 <= sequence <= 0xFFFFFFFF
        ):
            return FusionExecutionResult.INVALID
        previous = self._watermarks.get((namespace, source))
        if previous is not None:
            delta = (sequence - previous[0]) & 0xFFFFFFFF
            if delta >= 0x80000000:
                return FusionExecutionResult.DISCONTINUITY
            if delta == 0 and previous[1] & mask:
                return FusionExecutionResult.DUPLICATE
        return FusionExecutionResult.COMPLETE

    def Commit(self, namespace, source, sequence, mask):
        previous = self._watermarks.get((namespace, source))
        bits = previous[1] if previous is not None and previous[0] == sequence else 0
        self._watermarks[(namespace, source)] = (sequence, bits | mask)

    def __len__(self):
        return len(self._watermarks)
