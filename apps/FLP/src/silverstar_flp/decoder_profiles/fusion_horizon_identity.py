"""Closed data identity for delayed-primary packages; no numerical selection."""

from collections.abc import Mapping

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

SCHEMA_ID = "silverstar.navigation.fusion_horizon"
VERSIONS = {
    "silverstar.algorithm.estimator.kf6": "0.4.0",
    "silverstar.algorithm.estimator.eskf15": "0.3.0",
}
ALGORITHMS = {
    "silverstar.algorithm.estimator.kf6": (1, 512),
    "silverstar.algorithm.estimator.eskf15": (2, 832),
}
ADDITIONAL_VERSIONS = {"silverstar.algorithm.estimator.eskf15": frozenset(("0.4.0",))}


def FusionHorizonVersionKnown_Is(component, version):
    return component in VERSIONS and (
        version == VERSIONS[component] or version in ADDITIONAL_VERSIONS.get(component, ())
    )


CONSTANTS = {
    "schema_id": SCHEMA_ID,
    "revision": 1,
    "mode": 2,
    "source_time": "resolved_measurement_epoch",
    "application_time": "resolved_measurement_epoch",
    "primary_time": "max(initial_epoch,estimator_present-horizon_us)",
    "evaluation_time": "estimator_present",
    "output_state_time": "estimator_present",
    "output_covariance_time": "estimator_present",
    "replays_history": False,
    "output_feedback": False,
    "body_capacity": 160,
    "event_capacity": 64,
}


def FusionHorizonDeclaration_Validate(declaration, component, version):
    if not FusionHorizonVersionKnown_Is(component, version):
        raise DecoderProfileError("fusion_horizon_component_version_unsupported")
    fields = {*CONSTANTS, "component", "horizon_us", "numerical_revision", "maximum_work"}
    if not isinstance(declaration, Mapping) or set(declaration) != fields:
        raise DecoderProfileError("fusion_horizon_declaration_invalid")
    for name, value in CONSTANTS.items():
        if type(declaration[name]) is not type(value) or declaration[name] != value:
            raise DecoderProfileError("fusion_horizon_declaration_mismatch:" + name)
    numerical, work = ALGORITHMS[component]
    if (
        declaration["component"] != component
        or type(declaration["numerical_revision"]) is not int
        or declaration["numerical_revision"] != numerical
        or type(declaration["maximum_work"]) is not int
        or declaration["maximum_work"] != work
    ):
        raise DecoderProfileError("fusion_horizon_algorithm_contract_mismatch")
    lag = declaration["horizon_us"]
    if type(lag) is not int or not 10000 <= lag <= 550000 or lag % 1000:
        raise DecoderProfileError("fusion_horizon_lag_invalid")
    return lag, numerical


def FusionHorizonActual_Validate(parameter_sets, component, horizon_us):
    if not isinstance(parameter_sets, (list, tuple)) or any(
        not isinstance(row, Mapping)
        or not isinstance(row.get("parameters", ()), (list, tuple))
        or any(not isinstance(p, Mapping) for p in row.get("parameters", ()))
        for row in parameter_sets
    ):
        raise DecoderProfileError("fusion_horizon_actual_sets_invalid")
    parameters = [
        p
        for row in parameter_sets
        if row.get("component") == component
        for p in row.get("parameters", ())
        if p.get("id") == "fusion_horizon_ms"
    ]
    if len(parameters) != 1:
        raise DecoderProfileError("fusion_horizon_actual_missing_or_ambiguous")
    p = parameters[0]
    if (
        type(p.get("value")) is not int
        or p["value"] * 1000 != horizon_us
        or p.get("storage_type") != "int32"
        or p.get("unit") != "ms"
        or p.get("representation") != "value"
    ):
        raise DecoderProfileError("fusion_horizon_actual_mismatch")
