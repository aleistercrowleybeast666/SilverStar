from __future__ import annotations

from dataclasses import replace

from silverstar_fccg.project.model import LogStreamConfig, ProjectModel
from silverstar_fccg.project.feature_tiers import FeatureTier_LogRecordAllowed, FeatureTier_LogRecordRequired


SF6_MINIMAL_RECORDS = frozenset("FLIGHT_LOG_RECORD_" + name for name in (
    "EVENT", "STATS", "SYSTEM_CONFIG", "HEALTH",
    "INITIAL_STATE", "BARO_NATIVE", "INERTIAL_INCREMENT",
    "IMU_CORRECTED", "CALIBRATION_RESULT", "ALIGNMENT_RESULT", "MISSION_CONFIG",
    "DEVICE_DESCRIPTOR", "ALGORITHM_DESCRIPTOR", "LOG_STREAM_DESCRIPTOR",
    "DECODER_PROFILE_DESCRIPTOR", "LANDING_DIAGNOSTIC",
    "ALIGNMENT_EVIDENCE", "MISSION_SNAPSHOT_IDENTITY", "MAG_CALIBRATION_IDENTITY",
    "SF6_STATE", "SF6_MEASUREMENT", "PURE_INS",
))
SF6_MINIMUM_REQUIRED = SF6_MINIMAL_RECORDS - {
    "FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY",
}


def CompactLogStreams_Get(model: ProjectModel) -> list[LogStreamConfig]:
    """Apply the explicit profile without overwriting retained all-stream choices.

    The profile keeps the protocol cadence; SF6 outputs are mandatory within
    this profile even if the preceding algorithm left those streams disabled.
    All catalogue entries, including disabled entries, remain in the decoder
    and startup descriptor snapshot. GNSS diagnostics and other algorithm
    outputs are deliberately excluded and shown as disabled.
    """
    if model.build.logging_profile == "all_streams":
        return [replace(stream, enabled=False) if not FeatureTier_LogRecordAllowed(model, stream.record)
                else replace(stream, enabled=True) if FeatureTier_LogRecordRequired(model, stream.record) else stream
                for stream in model.logging_streams]
    required = CompactLogRequiredRecords_Get(model)
    return [replace(stream, enabled=(
        FeatureTier_LogRecordAllowed(model, stream.record) and
        stream.record in SF6_MINIMAL_RECORDS and
        (stream.enabled or stream.record in required) and
        (model.strategies.get("estimator") is not None or not stream.record.startswith("FLIGHT_LOG_RECORD_SF6_"))
    )) for stream in model.logging_streams]


def CompactLogRequiredRecords_Get(model: ProjectModel) -> frozenset[str]:
    if model.strategies.get("estimator") is None:
        return SF6_MINIMUM_REQUIRED - {"FLIGHT_LOG_RECORD_SF6_STATE", "FLIGHT_LOG_RECORD_SF6_MEASUREMENT"}
    return SF6_MINIMUM_REQUIRED - {"FLIGHT_LOG_RECORD_PURE_INS"}


def CompactLogProfileErrors_Get(model: ProjectModel, catalog=None) -> tuple[str, ...]:
    if model.build.logging_profile == "all_streams":
        return ()
    if model.build.logging_profile != "sf6_minimal":
        return ("Unknown compact logging profile",)
    if model.build.feature_tier != "minimal" or model.strategies.get("estimator") not in (None, "silverstar.algorithm.estimator.sf6"):
        return ("Minimal replay logging requires Minimal tier and SF6 or pure INS",)
    if model.protocols.get("logging") is None:
        return ("SF6 minimal logging requires the Logging Protocol and its storage contract",)
    if catalog is not None:
        from silverstar_fccg.project.logging import LogAvailability_Get, ProtocolLogDefinitions_Get
        unavailable = [definition.record for definition in ProtocolLogDefinitions_Get(model, catalog)
                       if definition.record in CompactLogRequiredRecords_Get(model)
                       and not LogAvailability_Get(definition, model, catalog).available]
        if unavailable:
            return ("SF6 minimal logging requires available raw IMU/barometer and lifecycle producers: "
                    + ", ".join(unavailable),)
    return ()
