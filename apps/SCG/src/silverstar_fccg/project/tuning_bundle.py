"""TreeDiagram research bundle around unchanged strict function-parameters/1.

Only the enclosed, selected-owner scalar profiles can be applied to a project.
The separate control research record never grants a mission/actuator consumer.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from silverstar_fccg.project.function_parameters import (
    ParameterProfile_Apply, ParameterProfileError, _Profile_Require,
)

SCHEMA_ID = "silverstar.tuning-bundle/1"
MAX_BYTES = 1048576


def TuningBundle_Digest(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "content_sha256"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _FiniteTree_Require(value, depth: int = 0) -> None:
    if depth > 16:
        raise ParameterProfileError("tuning_bundle_depth")
    if isinstance(value, dict):
        for item in value.values():
            _FiniteTree_Require(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 128:
            raise ParameterProfileError("tuning_bundle_array_capacity")
        for item in value:
            _FiniteTree_Require(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ParameterProfileError("tuning_bundle_nonfinite")


def TuningBundle_Validate(value: dict) -> dict:
    fields = {"schema_id", "schema_version", "model_id", "run_id", "coordinates",
        "implementation_identity", "profiles", "control_research", "limitations", "content_sha256"}
    if type(value) is not dict or set(value) != fields:
        raise ParameterProfileError("tuning_bundle_fields")
    _FiniteTree_Require(value)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BYTES:
        raise ParameterProfileError("tuning_bundle_size")
    if value["schema_id"] != SCHEMA_ID or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ParameterProfileError("tuning_bundle_version")
    if value["coordinates"] != "ENU; body+Z; Hamilton-wxyz; q_nb":
        raise ParameterProfileError("tuning_bundle_coordinates")
    for key in ("model_id", "run_id"):
        if type(value[key]) is not str or not 1 <= len(value[key]) <= 128:
            raise ParameterProfileError("tuning_bundle_identity:" + key)
    for key in ("implementation_identity", "content_sha256"):
        if type(value[key]) is not str or not re.fullmatch("[0-9a-f]{64}", value[key]):
            raise ParameterProfileError("tuning_bundle_digest:" + key)
    if type(value["profiles"]) is not list or len(value["profiles"]) > 8:
        raise ParameterProfileError("tuning_bundle_profiles")
    seen = set()
    for profile in value["profiles"]:
        _Profile_Require(profile)
        if profile["plugin_id"] in seen:
            raise ParameterProfileError("tuning_bundle_duplicate_owner")
        seen.add(profile["plugin_id"])
    if type(value["limitations"]) is not list or any(type(row) is not str or len(row) > 512 for row in value["limitations"]):
        raise ParameterProfileError("tuning_bundle_limitations")
    control = value["control_research"]
    if control is not None:
        if type(control) is not dict or set(control) != {"schema_id", "kind", "deployable", "parameters", "design"}:
            raise ParameterProfileError("tuning_bundle_control_fields")
        if control["schema_id"] != "silverstar.control-research/1" or control["deployable"] is not False:
            raise ParameterProfileError("tuning_bundle_missing_target_consumer")
        if control["kind"] not in ("pid", "lqr") or type(control["parameters"]) is not dict:
            raise ParameterProfileError("tuning_bundle_control_kind")
        keys = {"kp", "ki", "kd", "derivative_tau_s", "integral_limit", "output_limit", "sample_period_s"} if control["kind"] == "pid" else {"k_angle", "k_rate", "output_limit"}
        if set(control["parameters"]) != keys:
            raise ParameterProfileError("tuning_bundle_control_parameters")
        for number in control["parameters"].values():
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ParameterProfileError("tuning_bundle_control_number")
        if control["parameters"]["output_limit"] <= 0:
            raise ParameterProfileError("tuning_bundle_control_limit")
        if control["kind"] == "pid":
            if control["design"] is not None or any(control["parameters"][key] < 0 for key in keys) or control["parameters"]["sample_period_s"] <= 0:
                raise ParameterProfileError("tuning_bundle_pid_domain")
        else:
            design = control["design"]
            if type(design) is not dict or set(design) != {"a", "b", "q", "r", "k", "dt_s", "model_source", "state_order", "input_order", "storage_order", "riccati_residual", "closed_loop_radius"}:
                raise ParameterProfileError("tuning_bundle_lqr_design")
            if design["state_order"] != ["angle_error_rad", "angular_rate_radps"] or design["input_order"] != ["actuator_command"] or design["storage_order"] != "row_major":
                raise ParameterProfileError("tuning_bundle_lqr_order")
            for key, rows, columns in (("a", 2, 2), ("b", 2, 1), ("q", 2, 2), ("r", 1, 1), ("k", 1, 2)):
                matrix = design[key]
                if type(matrix) is not list or len(matrix) != rows or any(type(row) is not list or len(row) != columns or any(type(x) not in (int, float) or not math.isfinite(x) for x in row) for row in matrix):
                    raise ParameterProfileError("tuning_bundle_lqr_dimension:" + key)
            for key in ("dt_s", "riccati_residual", "closed_loop_radius"):
                if type(design[key]) not in (int, float) or not math.isfinite(design[key]):
                    raise ParameterProfileError("tuning_bundle_lqr_number:" + key)
            if design["dt_s"] <= 0 or not 0 <= design["riccati_residual"] <= 1e-8 or not 0 <= design["closed_loop_radius"] < 1:
                raise ParameterProfileError("tuning_bundle_lqr_solver")
            if type(design["model_source"]) is not str or not 1 <= len(design["model_source"]) <= 512:
                raise ParameterProfileError("tuning_bundle_lqr_model_source")
            if design["k"][0] != [control["parameters"]["k_angle"], control["parameters"]["k_rate"]]:
                raise ParameterProfileError("tuning_bundle_lqr_gain_mismatch")
            q, a, b, k = design["q"], design["a"], design["b"], design["k"][0]
            if abs(q[0][1] - q[1][0]) > 1e-12 or q[0][0] < -1e-12 or q[1][1] < -1e-12 or q[0][0]*q[1][1]-q[0][1]*q[1][0] < -1e-12 or design["r"][0][0] <= 0:
                raise ParameterProfileError("tuning_bundle_lqr_weight_domain")
            closed = [[a[i][j]-b[i][0]*k[j] for j in range(2)] for i in range(2)]
            trace = closed[0][0]+closed[1][1]
            determinant = closed[0][0]*closed[1][1]-closed[0][1]*closed[1][0]
            discriminant = trace*trace-4*determinant
            if not all(math.isfinite(x) for x in (trace, determinant, discriminant)):
                raise ParameterProfileError("tuning_bundle_lqr_closed_loop_numeric")
            radius = math.sqrt(determinant) if discriminant < 0 else max(abs((trace+math.sqrt(discriminant))/2), abs((trace-math.sqrt(discriminant))/2))
            if radius >= 1-1e-10 or abs(radius-design["closed_loop_radius"]) > 1e-7:
                raise ParameterProfileError("tuning_bundle_lqr_closed_loop")
    if TuningBundle_Digest(value) != value["content_sha256"]:
        raise ParameterProfileError("tuning_bundle_content_digest")
    return deepcopy(value)


def TuningBundle_Read(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ParameterProfileError("tuning_bundle_duplicate_key")
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ParameterProfileError("tuning_bundle_size")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ParameterProfileError("tuning_bundle_nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ParameterProfileError(str(error)) from error
    return TuningBundle_Validate(value)


def TuningBundle_Apply(model, catalog, value: dict):
    """Return an entirely validated candidate; the caller publishes once."""
    bundle = TuningBundle_Validate(value)
    candidate = deepcopy(model)
    shared = {}
    for profile in bundle["profiles"]:
        owner = catalog.Component_Get(profile["plugin_id"])
        supplied = {row["id"]: row["value"] for row in profile["parameters"]}
        for parameter in owner.algorithm_parameters:
            if parameter.shared_key and parameter.parameter_id in supplied:
                actual = parameter.Value_Resolve(supplied[parameter.parameter_id])
                if parameter.shared_key in shared and shared[parameter.shared_key] != actual:
                    raise ParameterProfileError("tuning_bundle_shared_conflict:" + parameter.shared_key)
                shared[parameter.shared_key] = actual
    for profile in bundle["profiles"]:
        candidate = ParameterProfile_Apply(candidate, catalog, profile["plugin_id"], profile)
    return candidate


def TuningBundle_Preview(model, catalog, value: dict) -> dict:
    bundle = TuningBundle_Validate(value)
    candidate = TuningBundle_Apply(model, catalog, bundle)
    changes = []
    for owner_id, values in candidate.algorithm_parameters.items():
        definitions = {row.parameter_id: row for row in catalog.Component_Get(owner_id).algorithm_parameters}
        for identity, after in values.items():
            before = model.algorithm_parameters.get(owner_id, {}).get(identity)
            if before != after:
                parameter = definitions[identity]
                changes.append({"plugin_id": owner_id, "parameter_id": identity,
                    "before": deepcopy(before), "after": deepcopy(after),
                    "unit": parameter.unit, "shared": bool(parameter.shared_key)})
    return {"changes": changes, "control_deployable": False,
        "control_status": "research only; no target mission/actuator consumer",
        "limitations": bundle["limitations"]}


def TuningBundle_ControlHeaderRender(value: dict) -> str:
    """Render bounded C config for explicit core tests; not a mission driver."""
    import struct
    bundle = TuningBundle_Validate(value)
    control = bundle["control_research"]
    if control is None:
        raise ParameterProfileError("tuning_bundle_no_control")
    def literal(number):
        try:
            actual = struct.unpack("<f", struct.pack("<f", number))[0]
        except (struct.error, OverflowError) as error:
            raise ParameterProfileError("tuning_bundle_control_float32") from error
        if not math.isfinite(actual):
            raise ParameterProfileError("tuning_bundle_control_float32")
        return f"{actual:.9e}f"
    parameters = control["parameters"]
    rows = ["#ifndef __PROJECT_CONTROL_RESEARCH_H", "#define __PROJECT_CONTROL_RESEARCH_H", "",
        "/* Mathematical test configuration only: no target actuator/mission consumer. */",
        f'/* Bundle content SHA-256: {bundle["content_sha256"]} */']
    if control["kind"] == "pid":
        rows += ['#include "control_pid.h"', "static inline ControlPidConfig ProjectControl_PidConfigGet(void)",
            "{", "    const ControlPidConfig config = {"]
        rows += [f"        .{key} = {literal(parameters[key])}," for key in
            ("kp", "ki", "kd", "derivative_tau_s", "integral_limit", "output_limit", "sample_period_s")]
    else:
        rows += ['#include "control_lqr.h"', "static inline ControlLqrConfig ProjectControl_LqrConfigGet(void)",
            "{", "    const ControlLqrConfig config = {",
            f'        .gain = {{{literal(parameters["k_angle"])}, {literal(parameters["k_rate"])}}},',
            f'        .output_limit = {literal(parameters["output_limit"])},']
    rows += ["    };", "    return config;", "}", "", "#endif", ""]
    return "\n".join(rows)


def TuningBundle_ControlCoreAttach(model, catalog, value: dict):
    """Explicitly include a mathematical core in normal generation, not dispatch.

    Its bounded scalar inputs enter the ordinary parameter owner and decoder.
    The richer controller design remains in the separate research bundle.
    """
    from silverstar_fccg.project.algorithm_parameters import (
        AlgorithmParameters_Reconcile, AlgorithmParameters_Resolve,
    )
    bundle = TuningBundle_Validate(value)
    control = bundle["control_research"]
    if control is None:
        raise ParameterProfileError("tuning_bundle_no_control")
    candidate = TuningBundle_Apply(model, catalog, bundle)
    plugin_id = "silverstar.algorithm.control." + control["kind"]
    owner = catalog.Component_Get(plugin_id)
    if owner.version != "0.1.0" or owner.metadata.get("deployment_ready") is not False:
        raise ParameterProfileError("tuning_bundle_control_core_identity")
    if plugin_id not in candidate.base_components:
        candidate.base_components.append(plugin_id)
    AlgorithmParameters_Reconcile(candidate, catalog)
    if set(control["parameters"]) != {row.parameter_id for row in owner.algorithm_parameters}:
        raise ParameterProfileError("tuning_bundle_control_core_parameter_set")
    for parameter in owner.algorithm_parameters:
        candidate.algorithm_parameters[plugin_id][parameter.parameter_id] = parameter.Value_Resolve(
            control["parameters"][parameter.parameter_id])
    AlgorithmParameters_Resolve(candidate, catalog)
    return candidate


def TuningBundle_Cli() -> int:
    import argparse
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.plugins.catalog import PluginCatalog
    from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
    parser = argparse.ArgumentParser(description="Preview/apply strict TreeDiagram scalar tuning profiles")
    parser.add_argument("action", choices=("preview", "apply"))
    parser.add_argument("project", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[3] / "plugins/builtin")
    parser.add_argument("--output", type=Path, help="Required for Apply; writes this explicit project path atomically")
    parser.add_argument("--include-control-core", action="store_true",
        help="Explicit mathematical build interface only; does not register a mission/actuator driver")
    args = parser.parse_args()
    if args.action == "apply" and args.output is None:
        parser.error("apply requires --output; preview never writes")
    try:
        catalog = PluginCatalog(args.catalog, args.catalog.parent / "installed")
        catalog.Scan()
        model = ProjectModel_Load(args.project.resolve())
        bundle = TuningBundle_Read(args.bundle)
        preview = TuningBundle_Preview(model, catalog, bundle)
        if args.include_control_core:
            control_candidate = TuningBundle_ControlCoreAttach(model, catalog, bundle)
            owner_id = "silverstar.algorithm.control." + bundle["control_research"]["kind"]
            preview["control_core_preview"] = {"plugin_id": owner_id,
                "before": model.algorithm_parameters.get(owner_id),
                "after": control_candidate.algorithm_parameters[owner_id],
                "compile_mathematical_interface": True, "runtime_dispatch": False}
        if args.action == "apply":
            candidate = (TuningBundle_ControlCoreAttach(model, catalog, bundle)
                if args.include_control_core else TuningBundle_Apply(model, catalog, bundle))
            output = args.output.resolve()
            ProjectModel_Save(candidate, output, WorkspacePolicy(output.parent))
            preview["output"] = str(output)
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(TuningBundle_Cli())
