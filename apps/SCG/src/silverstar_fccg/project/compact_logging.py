from __future__ import annotations

from dataclasses import replace

from silverstar_fccg.project.model import LogStreamConfig, ProjectModel


SF6_MINIMAL_RECORDS = frozenset("FLIGHT_LOG_RECORD_" + name for name in (
    "EVENT", "STATS", "SYSTEM_CONFIG", "HEALTH", "TELEMETRY_DIAG",
    "INITIAL_STATE", "BARO_NATIVE", "INERTIAL_INCREMENT", "BARO_MEASUREMENT",
    "IMU_CORRECTED", "CALIBRATION_RESULT", "ALIGNMENT_RESULT", "MISSION_CONFIG",
    "DEVICE_DESCRIPTOR", "ALGORITHM_DESCRIPTOR", "LOG_STREAM_DESCRIPTOR",
    "DECODER_PROFILE_DESCRIPTOR", "ESTIMATOR_STEP", "LANDING_DIAGNOSTIC",
    "ALIGNMENT_EVIDENCE", "MISSION_SNAPSHOT_IDENTITY", "MAG_CALIBRATION_IDENTITY",
    "SF6_STATE", "SF6_MEASUREMENT",
))
SF6_MINIMUM_REQUIRED = SF6_MINIMAL_RECORDS - {
    "FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY",
    "FLIGHT_LOG_RECORD_TELEMETRY_DIAG",
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
        return model.logging_streams
    return [replace(stream, enabled=(
        stream.record in SF6_MINIMAL_RECORDS and
        (stream.enabled or stream.record in SF6_MINIMUM_REQUIRED)
    )) for stream in model.logging_streams]


def CompactLogProfileErrors_Get(model: ProjectModel, catalog=None) -> tuple[str, ...]:
    if model.build.logging_profile == "all_streams":
        return ()
    if model.build.logging_profile != "sf6_minimal":
        return ("Unknown compact logging profile",)
    if not model.build.compact_mode or model.strategies.get("estimator") != "silverstar.algorithm.estimator.sf6":
        return ("SF6 minimal logging requires explicit compact mode and SF6",)
    if model.protocols.get("logging") is None:
        return ("SF6 minimal logging requires the Logging Protocol and its storage contract",)
    if catalog is not None:
        from silverstar_fccg.project.logging import LogAvailability_Get, ProtocolLogDefinitions_Get
        unavailable = [definition.record for definition in ProtocolLogDefinitions_Get(model, catalog)
                       if definition.record in SF6_MINIMUM_REQUIRED
                       and not LogAvailability_Get(definition, model, catalog).available]
        if unavailable:
            return ("SF6 minimal logging requires available raw IMU/barometer and lifecycle producers: "
                    + ", ".join(unavailable),)
    return ()
