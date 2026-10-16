"""Data-only timing identity; never selects or implements a numerical algorithm."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.fusion_horizon_identity import (
    SCHEMA_ID as HORIZON_SCHEMA_ID,
)
from silverstar_flp.decoder_profiles.fusion_horizon_identity import (
    FusionHorizonActual_Validate,
    FusionHorizonDeclaration_Validate,
    FusionHorizonVersionKnown_Is,
)

SCHEMA_ID = "silverstar.navigation-fusion-timing/1"
PARAMETER_ID = "fusion_timing_mode"
LEGACY_VERSIONS = {
    "silverstar.algorithm.estimator.kf6": frozenset(("0.1.0", "0.2.0", "0.2.1")),
    "silverstar.algorithm.estimator.eskf15": frozenset(("0.1.0", "0.1.1")),
}
TIMING_VERSIONS = {
    "silverstar.algorithm.estimator.kf6": "0.3.0",
    "silverstar.algorithm.estimator.eskf15": "0.2.0",
}
PREDICTION_ADAPTER = {
    "component": "silverstar.algorithm.estimator.kf6",
    "component_version": "0.3.0",
    "fusion_timing_mode": 0,
    "record": "ESTIMATOR_STEP",
    "record_id": 30,
    "record_version": 0,
    "result_field": "replay_result",
    "result_namespace": "legacy_navigation_replay_result_used_for_current_prediction_adapter",
    "reachable_results": [0, 1, 4, 5, 6],
    "committed_results": [0],
    "fault_latched_results": [4, 5, 6],
    "not_called_when": {"attitude_result": 0},
    "history_replay_executed": False,
}
_FIELDS = frozenset(
    (
        "schema_id",
        "revision",
        "component",
        "mode",
        "source_time",
        "application_time",
        "evaluation_time",
        "output_state_time",
        "output_covariance_time",
        "replays_history",
    )
)


@dataclass(frozen=True)
class FusionTimingIdentity:
    component: str
    version: str | None
    revision: int | None
    mode: int | None
    evidence: str
    unavailable_reason: str = ""
    horizon_us: int | None = None
    numerical_revision: int | None = None


def FusionTimingVersionKnown_Is(identity):
    return bool(
        identity
        and identity.component in TIMING_VERSIONS
        and identity.version
        and (identity.version == TIMING_VERSIONS.get(identity.component) or
             FusionHorizonVersionKnown_Is(identity.component, identity.version))
    )


def _Version_Get(document: Mapping, component: str) -> str | None:
    locks = document.get("component_locks", ())
    if not isinstance(locks, (list, tuple)) or any(not isinstance(row, Mapping) for row in locks):
        raise DecoderProfileError("fusion_timing_component_locks_invalid")
    selected = [row for row in locks if row.get("component") == component]
    if len(selected) > 1:
        raise DecoderProfileError("fusion_timing_component_identity_ambiguous")
    if not selected:
        return None
    version = selected[0].get("version")
    if not isinstance(version, str) or not version:
        raise DecoderProfileError("fusion_timing_component_version_invalid")
    return version


def _Declaration_Validate(declaration: object, component: str) -> int:
    if not isinstance(declaration, Mapping) or set(declaration) != _FIELDS:
        raise DecoderProfileError("fusion_timing_declaration_invalid")
    if (
        declaration["schema_id"] != SCHEMA_ID
        or type(declaration["revision"]) is not int
        or declaration["revision"] != 1
    ):
        raise DecoderProfileError("fusion_timing_revision_unsupported")
    if declaration["component"] != component:
        raise DecoderProfileError("fusion_timing_component_mismatch")
    mode = declaration["mode"]
    if type(mode) is not int or mode not in (0, 1):
        raise DecoderProfileError("fusion_timing_mode_unsupported")
    expected = {
        "source_time": "resolved_measurement_epoch",
        "application_time": "estimator_present" if mode == 0 else "legacy_algorithm_epoch",
        "evaluation_time": "estimator_present",
        "output_state_time": "estimator_present",
        "output_covariance_time": "estimator_present",
    }
    if any(declaration[key] != value for key, value in expected.items()):
        raise DecoderProfileError("fusion_timing_timestamp_contract_mismatch")
    if type(declaration["replays_history"]) is not bool or declaration["replays_history"] != (
        mode == 1
    ):
        raise DecoderProfileError("fusion_timing_history_contract_mismatch")
    return mode


def FusionTiming_FromSemantics(document: Mapping) -> FusionTimingIdentity | None:
    """Missing declarations are legacy only for an audited component version.

    An explicit declaration is a package assertion, not proof of implementation
    or runtime record completeness. Runtime admission validates v2 records too.
    No defaults or parameter values are synthesized into the input document.
    """
    declarations = document.get("metadata_declarations", {})
    if not isinstance(declarations, Mapping):
        raise DecoderProfileError("fusion_timing_metadata_invalid")
    owners = [name for name in document.get("algorithms", ()) if name in LEGACY_VERSIONS]
    declared = "fusion_timing" in declarations
    if len(owners) > 1:
        if declared:
            raise DecoderProfileError("fusion_timing_owner_ambiguous")
        # Historical packages may describe more than one estimator. Their raw
        # records remain readable; do not invent a single timing owner or mode.
        return FusionTimingIdentity(
            "", None, None, None, "unknown", "fusion_timing_identity_unproven"
        )
    if not owners:
        if declared:
            raise DecoderProfileError("fusion_timing_owner_invalid")
        return None
    component = owners[0]
    version = _Version_Get(document, component)
    from silverstar_flp.decoder_profiles.gnss_reacquisition import GnssReacquisition_FromSemantics
    GnssReacquisition_FromSemantics(document, component, version)
    legacy = version in LEGACY_VERSIONS[component]
    current_contract = version == TIMING_VERSIONS[component] or FusionHorizonVersionKnown_Is(
        component, version
    )
    if not declared:
        if current_contract:
            raise DecoderProfileError("fusion_timing_declaration_missing")
        return FusionTimingIdentity(
            component,
            version,
            0 if legacy else None,
            1 if legacy else None,
            "legacy_component_lock" if legacy else "unknown",
            "" if legacy else "fusion_timing_identity_unproven",
        )
    declaration = declarations["fusion_timing"]
    horizon_us = numerical = None
    if isinstance(declaration, Mapping) and declaration.get("schema_id") == HORIZON_SCHEMA_ID:
        horizon_us, numerical = FusionHorizonDeclaration_Validate(declaration, component, version)
        mode = 2
    else:
        mode = _Declaration_Validate(declaration, component)
    if legacy and mode != 1:
        raise DecoderProfileError("fusion_timing_legacy_component_mismatch")
    if current_contract:
        sets = document.get("firmware_algorithm_parameters", ())
        parameters = [
            p
            for row in sets
            if row.get("component") == component
            for p in row.get("parameters", ())
            if p.get("id") == PARAMETER_ID
        ]
        if len(parameters) != 1:
            raise DecoderProfileError("fusion_timing_actual_parameter_missing_or_ambiguous")
        parameter = parameters[0]
        if (
            type(parameter.get("value")) is not int
            or parameter["value"] != mode
            or parameter.get("storage_type") != "int32"
            or parameter.get("unit") != "1"
            or parameter.get("representation") != "value"
        ):
            raise DecoderProfileError("fusion_timing_actual_parameter_mismatch")
        if mode == 2:
            FusionHorizonActual_Validate(sets, component, horizon_us)
        if component.endswith("kf6") and mode == 0:
            adapter = declarations.get("fusion_prediction_adapter")

            # Frozen semantic contexts normalize arrays to tuples.
            def normalize(value):
                if isinstance(value, Mapping):
                    return {key: normalize(item) for key, item in value.items()}
                if isinstance(value, (list, tuple)):
                    return [normalize(item) for item in value]
                return value

            expected_adapter = {**PREDICTION_ADAPTER, "component_version": version}
            if normalize(adapter) != expected_adapter:
                raise DecoderProfileError("fusion_timing_prediction_adapter_identity_invalid")
    reason = "" if legacy or current_contract else "fusion_timing_identity_unproven"
    return FusionTimingIdentity(
        component, version, 1, mode, "explicit_declaration", reason, horizon_us, numerical
    )


def FusionTimingUnavailable_Get(dataset) -> tuple[str, ...]:
    """Return numerical replay blockers without altering raw records or bytes."""
    context = getattr(dataset, "semantic_context", None)
    if context is None:
        return ()  # Existing non-package/What-if admission remains independently checked.
    document = getattr(context, "raw_metadata", {})
    if not isinstance(document, Mapping):
        return ("fusion_timing_metadata_invalid",)
    declarations = document.get("metadata_declarations", {})
    if isinstance(declarations, Mapping) and "fusion_timing" not in declarations:
        # No new declaration means no new admission rule. Existing algorithm
        # revision/recorded-parameter checks retain authority over legacy replay.
        # This does not certify an unknown timing identity as exact replay.
        return ()
    try:
        identity = FusionTiming_FromSemantics(document)
        if identity and identity.mode == 2:
            from silverstar_flp.decoder_profiles.fusion_horizon_records import (
                FusionHorizonRecords_Validate,
            )

            evidence = FusionHorizonRecords_Validate(
                dataset,
                algorithm_id=2 if identity.component.endswith("eskf15") else 1,
                horizon_us=identity.horizon_us,
            )
            if evidence.replay_blockers:
                return evidence.replay_blockers
            required = (
                ("ESKF15_BODY_INPUT", "ESKF15_INITIAL_STATE", "ESKF15_INITIAL_P_PART")
                if identity.component.endswith("eskf15")
                else ("INERTIAL_INCREMENT", "ESTIMATOR_STEP", "ESTIMATOR", "KF6_FULL_P")
            )
            missing = tuple(
                "fusion_horizon_record_required:" + name
                for name in required
                if not dataset.Records_Get(name)
            )
            if missing:
                return missing
        elif FusionTimingVersionKnown_Is(identity):
            from silverstar_flp.decoder_profiles.fusion_timing_records import (
                FusionTimingRecords_Validate,
            )

            FusionTimingRecords_Validate(dataset)
            required = (
                ("ESKF15_MEASUREMENT",)
                if identity.component.endswith("eskf15")
                else ("GNSS_MEASUREMENT", "BARO_MEASUREMENT")
            )
            records = [r for name in required for r in dataset.Records_Get(name)]
            if not records or any(r.record_version != 2 for r in records):
                return ("fusion_timing_v2_records_required",)
            if identity.mode == 0:
                from silverstar_flp.decoder_profiles.fusion_timing_records import (
                    FusionTimingCurrentPackets_Validate,
                )

                FusionTimingCurrentPackets_Validate(dataset)
    except DecoderProfileError as error:
        return (str(error),)
    return (identity.unavailable_reason,) if identity and identity.unavailable_reason else ()


def FusionTimingRun_Resolve(dataset, parameters):
    """Select execution only after parameter resolution, without mutating records."""
    selected = parameters.get(PARAMETER_ID, 1)
    if type(selected) is not int or selected not in (0, 1, 2):
        raise ValueError("fusion_timing_mode_unsupported")
    context = getattr(dataset, "semantic_context", None)
    identity = FusionTiming_FromSemantics(getattr(context, "raw_metadata", {}))
    if selected == 2:
        if not FusionTimingVersionKnown_Is(identity) or identity.mode != 2:
            raise ValueError("fusion_horizon_recorded_mode2_identity_required")
        lag = parameters.get("fusion_horizon_ms")
        if type(lag) is not int or not 10 <= lag <= 550:
            raise ValueError("fusion_horizon_selected_lag_required")
        blockers = FusionTimingUnavailable_Get(dataset)
        if blockers:
            raise ValueError(",".join(blockers))
    elif identity and identity.mode == 2:
        raise ValueError("fusion_horizon_cross_mode_operation_conversion_unavailable")
    elif selected == 0:
        if not FusionTimingVersionKnown_Is(identity):
            raise ValueError("fusion_timing_current_v2_identity_required")
        blockers = FusionTimingUnavailable_Get(dataset)
        if blockers:
            raise ValueError(",".join(blockers))
        from silverstar_flp.decoder_profiles.fusion_timing_records import (
            FusionTimingCurrentPackets_Validate,
        )

        FusionTimingCurrentPackets_Validate(dataset)
    return selected, {
        "fusion_timing_mode": selected,
        "recorded_fusion_timing_mode": identity.mode if identity else None,
        "fusion_timing_identity_evidence": identity.evidence if identity else "unavailable",
        "fusion_timing_mode_parameter_recorded": FusionTimingVersionKnown_Is(identity),
        "fusion_source_time": "resolved_measurement_epoch",
        "fusion_application_time": "resolved_measurement_epoch"
        if selected == 2
        else "estimator_present"
        if selected == 0
        else "legacy_algorithm_epoch",
        "fusion_output_time": "estimator_present",
        **(
            {
                "recorded_horizon_us": identity.horizon_us,
                "selected_horizon_us": parameters["fusion_horizon_ms"] * 1000,
                "fusion_primary_time": "max(initial_epoch,estimator_present-horizon_us)",
                "fusion_numerical_revision": identity.numerical_revision,
            }
            if selected == 2
            else {}
        ),
    }
