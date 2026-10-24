"""Versioned SCG ActualParameters -> explicit What-if conversion, never Recorded.

Only trusted packaged field contracts are interpreted. A decoder package cannot
load code or declare its own conversion. Missing navigation state is supplied
explicitly by the caller, and its provenance remains user configuration.
"""
from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np

from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareParameters_Validate
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest

CONVERSION_VERSION = "silverstar.navigation.scg-what-if/1"
_AXES = "xyz"
_ORIGIN_FIELDS = {"kind", "provenance", "parameter_group", "initial_navigation", "dataset_identity"}


def _Plain(value):
    if isinstance(value, Mapping):
        return {key: _Plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_Plain(item) for item in value]
    return value


def _Contract_Get(model, manifest_sha256=None):
    # Trusted installed contracts only; preserve R2 logs, never accept decoder-
    # supplied conversion code or an unrecognized manifest/field extension.
    contracts = [json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
                 for name in ("firmware_contract_v2.json", "firmware_contract_v1.json")]
    for contract in contracts:
        row = contract["models"].get(model)
        if row is not None and (manifest_sha256 is None or row["manifest_sha256"] == manifest_sha256):
            return row
    raise ValueError("scg_model_or_manifest_unsupported")


def _Float32(value):
    if type(value) not in (int, float):
        raise ValueError("scg_finite_number_required")
    try:
        if not math.isfinite(value):
            raise ValueError("scg_finite_number_required")
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError("scg_float32_unrepresentable") from exc
    if not math.isfinite(result):
        raise ValueError("scg_float32_unrepresentable")
    return result


def _Parameters_Read(model, group):
    group = _Plain(group)
    contract = _Contract_Get(model, group.get("manifest_sha256"))
    try:
        FirmwareParameters_Validate([group], (contract["component"],))
    except (DecoderProfileError, OverflowError, TypeError) as exc:
        raise ValueError("scg_actual_parameters_invalid:" + getattr(exc, "code", type(exc).__name__)) from exc
    if group["manifest_sha256"] != contract["manifest_sha256"]:
        raise ValueError("scg_manifest_unsupported")
    entries = {item["id"]: item for item in group["parameters"]}
    if set(entries) != set(contract["parameters"]):
        raise ValueError("scg_parameter_fields")
    values = {}
    for name, spec in contract["parameters"].items():
        item = entries[name]
        if any(item[key] != spec[key] for key in ("unit", "representation", "storage_type")):
            raise ValueError("scg_parameter_contract:" + name)
        value = item["value"]
        if item["storage_type"] == "float32":
            if value != _Float32(value):
                raise ValueError("scg_parameter_not_actual_float32:" + name)
            lower, upper = _Float32(spec["minimum"]), _Float32(spec["maximum"])
        else:
            lower, upper = spec["minimum"], spec["maximum"]
        if not lower <= value <= upper:
            raise ValueError("scg_parameter_range:" + name)
        values[name] = value
    if (values["initialization_confirmed"] != 1 or values["software_validation_build"] != 1
            or values["gnss_imu_colocated_confirmed"] != 1):
        raise ValueError("scg_initialization_or_validation_unconfirmed")
    positive = ["gravity_mps2", "position_nis_gate", "velocity_nis_gate"]
    positive += ["initial_variance_" + str(i) for i in range(contract["dimension"])]
    if model != "inekf15":
        positive += ["magnetic_reference_ut", "magnetic_nis_gate", "magnetic_min_norm_ratio"]
        if values["magnetic_max_norm_ratio"] <= values["magnetic_min_norm_ratio"]:
            raise ValueError("scg_magnetic_norm_order")
    if any(values[name] <= 0 for name in positive):
        raise ValueError("scg_positive_parameter_required")
    return values, contract, group


def _Vector32(value, size):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError("scg_initial_vector_shape")
    return np.asarray([_Float32(item) for item in value], dtype=np.float64)


def _QuaternionRotation(value):
    q = _Vector32(value, 4)
    norm2 = float(q @ q)
    if not .5 <= norm2 <= 1.5:
        raise ValueError("scg_initial_quaternion_norm")
    w, x, y, z = q / math.sqrt(norm2)
    return [[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
            [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
            [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]]


def _BaseConfiguration_Build(model, group, initial_navigation, observations):
    values, contract, group = _Parameters_Read(model, group)
    initial_navigation = _Plain(initial_navigation)
    if (not isinstance(initial_navigation, dict) or set(initial_navigation) != {
            "q_nb_wxyz", "origin_velocity_enu_mps", "provenance"}
            or initial_navigation["provenance"] != "user_configuration"):
        raise ValueError("scg_explicit_initial_navigation_required")
    initial = {
        "rotation": _QuaternionRotation(initial_navigation["q_nb_wxyz"]),
        "position": [0., 0., 0.],  # Backend_InitialBuild zeros the chosen local origin.
        "velocity": _Vector32(initial_navigation["origin_velocity_enu_mps"], 3).tolist(),
        "gyro_bias": [values["initial_gyro_bias_" + axis] for axis in _AXES],
        "accel_bias": [values["initial_accel_bias_" + axis] for axis in _AXES],
        "covariance": np.diag([values["initial_variance_" + str(i)]
                               for i in range(contract["dimension"])]).tolist(),
    }
    if model != "inekf15":
        initial.update(installation=_QuaternionRotation([values["installation_q_" + str(i)] for i in range(4)]),
                       inclination=values["inclination_rad"], declination=values["declination_rad"])
    noise = {}
    for source, target in (
        ("gyro", "gyro_radps_per_sqrt_hz"), ("accel", "accel_mps2_per_sqrt_hz"),
        ("gyro_bias_rw", "gyro_bias_rw_radps2_per_sqrt_hz"),
        ("accel_bias_rw", "accel_bias_rw_mps3_per_sqrt_hz")):
        noise[target] = [values[source + "_density_" + axis] for axis in _AXES]
    if not isinstance(observations, (tuple, list)) or len(observations) > 4096:
        raise ValueError("scg_observations_invalid")
    converted = []
    for original in observations:
        row = _Plain(original)
        if not isinstance(row, dict) or row.get("kind") not in ("position", "velocity", "magnetic"):
            raise ValueError("scg_observation_kind")
        kind = row["kind"]
        if kind == "magnetic" and model == "inekf15":
            raise ValueError("inekf15_has_no_magnetic_observation")
        bound = {"gate": values[kind + "_nis_gate"]}
        if kind == "magnetic":
            if type(row.get("source")) is not int or row["source"] & 255 != values["magnetic_instance"]:
                raise ValueError("scg_magnetic_instance_mismatch")
            bound.update(reference_strength_uT=values["magnetic_reference_ut"],
                         ratio_bounds=[values["magnetic_min_norm_ratio"], values["magnetic_max_norm_ratio"]])
        for key, value in bound.items():
            if key in row and row[key] != value:
                raise ValueError("scg_observation_parameter_override:" + key)
            row[key] = value
        converted.append(row)
    return {"schema": "silverstar.navigation.host-reference/1", "initial": initial,
            "gravity_enu": [0., 0., -values["gravity_mps2"]], "noise_density": noise,
            "observations": converted}


def ConfigurationOrigin_Validate(model, configuration):
    """Prevent edited JSON from retaining a stale conversion provenance claim."""
    origin = configuration["configuration_origin"]
    if (not isinstance(origin, dict) or set(origin) != _ORIGIN_FIELDS
            or origin["kind"] != CONVERSION_VERSION or origin["provenance"] != "Derived/user configuration"):
        raise ValueError("scg_configuration_origin_invalid")
    identity = origin["dataset_identity"]
    if identity is not None:
        if not isinstance(identity, dict) or set(identity) != {
                "parse_identity", "package_sha256", "generation_profile_sha256", "source_log_sha256"}:
            raise ValueError("scg_configuration_dataset_identity")
        parse = identity["parse_identity"]
        if (not isinstance(parse, dict) or set(parse) != {
                "schema", "log_sha256", "log_bytes", "decoder", "parser_identity"}
                or parse["schema"] != "silverstar.flp.full-dataset/1"
                or type(parse["log_bytes"]) is not int or parse["log_bytes"] < 0
                or not isinstance(parse["decoder"], dict)
                or parse["log_sha256"] != identity["source_log_sha256"]
                or any(parse["decoder"].get(key) != identity[key]
                       for key in ("package_sha256", "generation_profile_sha256"))
                or any(not isinstance(identity[key], str) or len(identity[key]) != 64
                       for key in ("package_sha256", "generation_profile_sha256", "source_log_sha256"))):
            raise ValueError("scg_configuration_dataset_identity")
    expected = _BaseConfiguration_Build(model, origin["parameter_group"], origin["initial_navigation"],
                                         configuration["observations"])
    # The optional body assumption is separately declared user input, never an
    # actual firmware parameter or part of the conversion's evidence claim.
    actual = {key: value for key, value in configuration.items()
              if key not in ("configuration_origin", "body_input_assumption")}
    if actual != expected:
        raise ValueError("scg_configuration_origin_mismatch")


def ScgWhatIfRequest_Build(model, parameter_group, initial_navigation, observations=(), *,
                          dataset_identity=None, body_input_assumption=None):
    configuration = _BaseConfiguration_Build(model, parameter_group, initial_navigation, observations)
    if body_input_assumption is not None:
        configuration["body_input_assumption"] = _Plain(body_input_assumption)
    configuration["configuration_origin"] = {
        "kind": CONVERSION_VERSION, "provenance": "Derived/user configuration",
        "parameter_group": _Plain(parameter_group), "initial_navigation": _Plain(initial_navigation),
        "dataset_identity": _Plain(dataset_identity),
    }
    text = json.dumps(configuration, allow_nan=False, sort_keys=True)
    from .plugin import _Configuration_Read, _Observations_Build
    _Configuration_Read(model, text)
    request = ReplayRequest(ReplayMode.WHAT_IF, "corrected_imu", {"configuration_json": text})
    _Observations_Build(model, configuration["observations"], request)
    return request


def ScgWhatIfRequest_FromDataset(dataset, model, initial_navigation, observations=(), *, body_input_assumption=None):
    contract = _Contract_Get(model)
    context = dataset.semantic_context
    if context is None or not dataset.metadata.get("parse_identity") or not dataset.metadata.get("source_log_sha256"):
        raise ValueError("scg_exact_log_open_required")
    if contract["component"] not in context.firmware_algorithm_ids:
        raise ValueError("scg_firmware_membership_missing")
    groups = [group for group in context.FirmwareParameterSets_Get() if group["component"] == contract["component"]]
    if len(groups) != 1:
        raise ValueError("scg_actual_parameter_set_missing_or_ambiguous")
    identity = {"parse_identity": dataset.metadata["parse_identity"],
        "source_log_sha256": dataset.metadata["source_log_sha256"],
        "package_sha256": context.package_identity.package_sha256,
        "generation_profile_sha256": context.package_identity.generation_profile_sha256}
    return ScgWhatIfRequest_Build(model, groups[0], initial_navigation, observations,
                                 dataset_identity=identity, body_input_assumption=body_input_assumption)


def ConfigurationDataset_Validate(dataset, configuration):
    """A package-bound conversion cannot silently claim another replay input."""
    origin = configuration["configuration_origin"]
    identity = origin["dataset_identity"]
    if identity is None:
        return  # Explicit standalone supplied parameters, without a package claim.
    context = getattr(dataset, "semantic_context", None)
    if context is None:
        raise ValueError("scg_configuration_dataset_mismatch")
    actual = {"parse_identity": dataset.metadata.get("parse_identity"),
              "source_log_sha256": dataset.metadata.get("source_log_sha256"),
              "package_sha256": context.package_identity.package_sha256,
              "generation_profile_sha256": context.package_identity.generation_profile_sha256}
    groups = [_Plain(group) for group in context.FirmwareParameterSets_Get()
              if group["component"] == origin["parameter_group"]["component"]]
    if _Plain(actual) != identity or groups != [origin["parameter_group"]]:
        raise ValueError("scg_configuration_dataset_mismatch")


def ScgRecordedBlockers_Get(model):
    blockers = ("augmented_full_initial_snapshot_not_recorded", "augmented_full_covariance_snapshot_not_recorded",
                "augmented_body_input_and_operation_contract_not_bound")
    if model != "inekf15":
        blockers += ("augmented_magnetic_calibration_installation_and_time_not_bound",)
    return blockers


def ConfigurationOriginAudit_Get(configuration):
    origin = configuration.get("configuration_origin")
    if origin is None:
        return {}
    digest = hashlib.sha256(json.dumps(origin["parameter_group"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"configuration_origin": origin, "scg_actual_parameters_sha256": digest,
            "scg_conversion_contract_sha256": hashlib.sha256(Path(__file__).with_name("firmware_contract_v1.json").read_bytes()).hexdigest(),
            "initial_position_basis": "backend zero at explicit local origin; no antenna lever-arm correction",
            "initial_navigation_provenance": "user_configuration; binary32 input conversion"}
