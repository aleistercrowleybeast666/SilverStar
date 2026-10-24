"""Explicit-input FLP host replays for three independent navigation models.

These float64 implementations are not MCU equivalents. InEKF means invariant.
Recorded requires an exact package and complete sealed v1 operation journal.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.mission import MissionReplayBounds_Get
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability, AlgorithmConfigurationAvailability, AlgorithmMetadata,
    AlgorithmPlugin, AlgorithmResult, EstimatorVisualizationSpec, FullCovarianceSpec,
    ParameterSpec, ReplayFidelity, ReplayMode, StateGroupSpec,
)
from .body_inputs import Assumption_Validate, BodySourceEnd_Get, BodySteps_Build

from .eskf20_reference import Eskf20State
from .inekf15_reference import InEkf15State
from .inekf20_reference import InEkf20State
from .input_reference import Event, Identity, ReferenceSession, Result, unsigned
from .buffered_replay import BufferedSession,result_label
from .lie_group import Array_Validate, Scalar_Validate

VERSION = "0.3.0-quality-journal-v2"
CONFIG_SOURCE = "Explicit offline navigation configuration"
_LIMIT = 4 * 1024 * 1024
_MODELS = {"eskf20": ("ESKF20", 20), "inekf15": ("InEKF15", 15),
           "inekf20": ("InEKF20", 20)}


def _Json_Read(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("navigation_explicit_configuration_required")
    if len(text.encode("utf-8")) > _LIMIT:
        raise ValueError("navigation_configuration_too_large")
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("navigation_configuration_duplicate_key")
            output[key] = value
        return output
    def constant(_value):
        raise ValueError("navigation_configuration_nonfinite")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _State_Build(model, initial):
    common = {"rotation", "position", "velocity", "gyro_bias", "accel_bias", "covariance"}
    extra = {"installation", "inclination", "declination"} if model != "inekf15" else set()
    if not isinstance(initial, dict) or set(initial) != common | extra:
        raise ValueError("navigation_initial_state_fields")
    if model == "eskf20":
        return Eskf20State(**initial)
    group = np.eye(5)
    group[:3, :3] = Array_Validate(initial["rotation"], (3, 3))
    group[:3, 3] = Array_Validate(initial["velocity"], (3,))
    group[:3, 4] = Array_Validate(initial["position"], (3,))
    values = {
        name: initial[name] for name in {"gyro_bias", "accel_bias", "covariance"} | extra}
    return (InEkf15State if model == "inekf15" else InEkf20State)(group=group, **values)


def _Configuration_Read(model, text):
    config = _Json_Read(text)
    required = {"schema", "initial", "gravity_enu", "noise_density", "observations"}
    if (not isinstance(config, dict) or not required <= set(config) <= required | {"configuration_origin", "body_input_assumption"}
            or config["schema"] != "silverstar.navigation.host-reference/1"):
        raise ValueError("navigation_configuration_schema")
    state = _State_Build(model, config["initial"])
    gravity = Array_Validate(config["gravity_enu"], (3,))
    noise = config["noise_density"]
    order = ("gyro_radps_per_sqrt_hz", "accel_mps2_per_sqrt_hz",
             "gyro_bias_rw_radps2_per_sqrt_hz", "accel_bias_rw_mps3_per_sqrt_hz")
    if not isinstance(noise, dict) or set(noise) != set(order):
        raise ValueError("navigation_named_noise_density_required")
    density = np.concatenate([Array_Validate(noise[name], (3,)) for name in order])
    if np.any(density < 0):
        raise ValueError("navigation_noise_density_negative")
    observations = config["observations"]
    if not isinstance(observations, list) or len(observations) > 4096:
        raise ValueError("navigation_observations_invalid")
    Assumption_Validate(config.get("body_input_assumption"))
    if "configuration_origin" in config:
        from .firmware_configuration import ConfigurationOrigin_Validate
        ConfigurationOrigin_Validate(model, config)
    return state, gravity, density, observations


def _BodyInputs_Get(dataset, assumption=None):
    if dataset.semantic_context is None or not dataset.metadata.get("parse_identity"):
        raise ValueError("navigation_exact_log_open_required")
    if dataset.start_timestamp_us is None or dataset.initial_state is None:
        raise ValueError("navigation_start_initial_state_required")
    calibration = dataset.semantic_context.calibration
    if not calibration.ready or not calibration.correction_valid:
        raise ValueError("navigation_frozen_imu_calibration_required")
    bounds = MissionReplayBounds_Get(dataset, source_end_timestamp_us=BodySourceEnd_Get(dataset))
    Assumption_Validate(assumption)
    if assumption is not None and assumption["calibration_generation"] != calibration.start_sequence:
        raise ValueError("navigation_body_assumed_generation_mismatch")
    steps, failure, exact = BodySteps_Build(dataset, bounds, assumption)
    if failure is not None:
        raise ValueError("navigation_body_input_invalid:" + failure["reason"])
    if not steps or steps[0].start_us != bounds.start_timestamp_us:
        raise ValueError("navigation_body_input_start_gap")
    source, generation = steps[0].source, steps[0].generation
    if source != calibration.source_id:
        raise ValueError("navigation_body_source_mismatch")
    if generation != calibration.start_sequence:
        raise ValueError("navigation_body_generation_mismatch")
    if exact:
        frozen = dataset.RecordAtOrBefore_Get("ESKF15_INITIAL_STATE", steps[0].start_us)
        if frozen is None or (source, generation) != (
            frozen.payload["source_id"], frozen.payload["calibration_generation"]
        ) or generation != calibration.start_sequence:
            raise ValueError("navigation_body_frozen_generation_mismatch")
    previous = bounds.start_timestamp_us
    for step in steps:
        if step.start_us != previous or step.source != source or step.generation != generation:
            raise ValueError("navigation_body_identity_or_continuity")
        if not 0 < step.end_us - step.start_us <= 20000:
            raise ValueError("navigation_body_interval_domain")
        if step.quality_flags != 0:
            # No silent reuse of ESKF15's unported quality/noise scaling policy.
            raise ValueError("navigation_body_quality_policy_unsupported")
        for value in (step.gyro1, step.gyro2, step.accel1, step.accel2):
            Array_Validate(value, (3,))
        previous = step.end_us
    return steps, {"reader": "navigation_reference_v1.body_inputs.BodySteps_Build", "exact_body_record": exact,
        "body_input_assumption": assumption,
        "body_input_provenance": "Derived/unverified user assumption" if assumption is not None else "recorded body evidence",
        "half_interval_contract": "equal physical half durations; reconstructed means rounded to binary32",
        "source_id": source, "calibration_generation": calibration.start_sequence,
        "generation_scope": "per_body_record" if exact else ("explicit assumption bound to selected frozen calibration result" if assumption is not None else "per_corrected_record"),
        "start_us": bounds.start_timestamp_us, "end_us": previous,
        "requested_end_us": bounds.end_timestamp_us}


def _Observations_Build(model, records, request):
    """Schema v1 vectors are IMU-origin ENU position (m) or velocity (m/s).

    A supplied vector is an explicit user assumption. No GNSS antenna lever arm
    or SCG installation is inferred or applied by this host implementation.
    """
    if records and request.mode != ReplayMode.WHAT_IF:
        raise ValueError("navigation_explicit_observations_require_what_if")
    parsed, identities = [], {}
    for row in records:
        common = {"kind", "epoch", "source", "calibration", "sample_us", "receive_us",
                  "sequence", "time_basis", "provenance", "value", "covariance", "gate"}
        mag = {"stage", "hard_iron_uT", "soft_iron", "reference_strength_uT", "ratio_bounds"}
        if not isinstance(row, dict) or row.get("kind") not in ("position", "velocity", "magnetic"):
            raise ValueError("navigation_observation_kind")
        kind = row["kind"]
        if kind == "magnetic" and model == "inekf15":
            raise ValueError("inekf15_has_no_magnetic_observation")
        if set(row) != common | (mag if kind == "magnetic" else set()):
            raise ValueError("navigation_observation_fields")
        if row["provenance"] != "user_configuration" or row["time_basis"] not in (
                "explicit_cotimed_assumption","explicit_measurement_clock_assumption"):
            raise ValueError("navigation_observation_provenance")
        identity = Identity(row["epoch"], row["source"], row["calibration"])
        for field in ("epoch", "source", "calibration", "sequence"):
            if not unsigned(row[field], 32):
                raise ValueError("navigation_observation_identity")
        if not unsigned(row["sample_us"], 64) or not unsigned(row["receive_us"], 64):
            raise ValueError("navigation_observation_time")
        if kind in identities and identities[kind] != identity:
            raise ValueError("navigation_observation_binding_changed")
        if Scalar_Validate(row["gate"]) <= 0:
            raise ValueError("navigation_observation_gate")
        identities[kind] = identity
        parsed.append((row, Event(identity, row["sample_us"], row["receive_us"], row["sequence"], 1)))
    return parsed, identities


def _FirmwareSpecs(model):
    from .firmware_configuration import _Contract_Get
    return tuple(ParameterSpec(name, "float" if row["storage_type"]=="float32" else "int", row.get("default", 0),
        row["minimum"], row["maximum"], unit=row["unit"], representation=row["representation"],
        description_code="firmware_actual_only") for name,row in _Contract_Get(model)["parameters"].items())


def _Metadata_Build(model):
    name, size = _MODELS[model]
    if model == "eskf20":
        groups = (("position", "m"), ("velocity", "m/s"), ("theta", "rad"),
                  ("gyro_bias", "rad/s"), ("accel_bias", "m/s^2"))
    else:
        groups = (("phi", "rad"), ("nu", "m/s"), ("rho", "m"),
                  ("gyro_bias_error", "rad/s"), ("accel_bias_error", "m/s^2"))
    symbols, units, specs = [], [], []
    for index, (group, unit) in enumerate(groups):
        names = tuple(f"{group}_{axis}" for axis in "xyz")
        symbols.extend(names); units.extend([unit] * 3)
        specs.append(StateGroupSpec(group, group, names, unit, f"{model}.covariance.diagonal",
                                    tuple(range(3 * index, 3 * index + 3))))
    if size == 20:
        for group, indexes in (("installation_residual", (15, 16, 17)), ("field_angles", (18, 19))):
            names = ("gamma_x", "gamma_y", "gamma_z") if len(indexes) == 3 else ("I", "D")
            symbols.extend(names); units.extend(["rad"] * len(indexes))
            specs.append(StateGroupSpec(group, group, names, "rad", f"{model}.covariance.diagonal", indexes))
    return AlgorithmMetadata(
        plugin_id=f"silverstar.algorithm.estimator.{model}", version=VERSION,
        display_name=name + (" (Invariant, offline)" if model.startswith("inekf") else " (offline)"),
        description=(f"{name} " + ("invariant EKF; " if model.startswith("inekf") else "")
            + "explicit-input float64 host replay; no firmware parity"),
        required_records=("INITIAL_STATE", "CALIBRATION_RESULT"),
        optional_records=("IMU_CORRECTED", "ESKF15_BODY_INPUT", "NAVIGATION_OPERATION_PART"), required_channels=(), optional_channels=(),
        parameter_schema=(ParameterSpec("configuration_json", "str", "", unit="1",
            description_code="navigation_explicit_initial_state_full_P_noise_gravity_and_observations"),),
        standard_outputs=("attitude.q_nb", "navigation.position_enu", "navigation.velocity_enu"),
        diagnostic_outputs=(f"{model}.covariance.diagonal", f"{model}.covariance.upper_triangle"),
        estimator_visualization=EstimatorVisualizationSpec(tuple(specs), (), FullCovarianceSpec(
            f"{model}.covariance.upper_triangle", f"{model}_full_P", tuple(symbols), tuple(units))),
        firmware_component_ids=(f"silverstar.algorithm.estimator.{model}",), recorded_output_roles=(),
        firmware_only_parameter_schema=_FirmwareSpecs(model),
        coordinate_frame_contract={"navigation_frame": "ENU", "quaternion_order": "WXYZ",
            "body_frame": "selected calibrated IMU", "magnetic_input": "sensor frame; A applied in model only",
            "vector_observation_point": "IMU origin; no antenna lever-arm correction",
            "vector_observation_units": "position ENU m; velocity ENU m/s"},
        parameter_source_contract={"offline": CONFIG_SOURCE, "recorded_configuration": "exact package actual parameters and sealed operation journal v1"},
        cadence_contract={"max_held_interval_us": 20000, "timing": "bounded true-time replay; 64 pairs/64 observations, maximum age 250000 us"},
    )


class NavigationReferenceAlgorithmPlugin(AlgorithmPlugin):
    def __init__(self, model):
        self.model = model
        self.metadata = _Metadata_Build(model)

    def OfflineParameters_Get(self):
        return {"configuration_json": ""}

    def availability(self, dataset, input_source=None):
        missing, sources = [], []
        if input_source not in (None,"navigation_journal","corrected_imu"):
            missing.append("navigation_input_source_unsupported")
        if input_source in (None,"navigation_journal"):
            try:
                from .recorded_journal import RecordedJournal_Read
                RecordedJournal_Read(dataset,self.model)
                sources.append("navigation_journal")
            except (ValueError,KeyError,TypeError) as exc:
                missing.append(str(exc))
        if input_source in (None,"corrected_imu"):
            try:
                _BodyInputs_Get(dataset)
                sources.append("corrected_imu")
            except (ValueError,KeyError,TypeError) as exc:
                missing.append(str(exc))
        return AlgorithmAvailability(bool(sources),
            ReplayFidelity.APPROXIMATE if sources else ReplayFidelity.UNAVAILABLE,
            () if sources else tuple(missing), ("host_reference_no_firmware_parity",), tuple(sources))

    def FirmwareConfiguration_WhatIfBuild(self, dataset, initial_navigation, observations=(), *, body_input_assumption=None):
        from .firmware_configuration import ScgWhatIfRequest_FromDataset
        return ScgWhatIfRequest_FromDataset(dataset, self.model, initial_navigation, observations, body_input_assumption=body_input_assumption)

    def ConfigurationAvailability_Get(self, dataset, *, input_available=True):
        try:
            from .recorded_journal import RecordedJournal_Read
            RecordedJournal_Read(dataset,self.model)
            return AlgorithmConfigurationAvailability(True,input_available,True,False,
                recorded_parameters={"configuration_json":""},offline_parameters=self.OfflineParameters_Get())
        except (ValueError,KeyError,TypeError) as exc:
            return AlgorithmConfigurationAvailability(False,input_available,self.FirmwareMember_Is(dataset),False,
                offline_parameters=self.OfflineParameters_Get(),missing_recorded_parameters=(str(exc),))

    def Parameters_Resolve(self, dataset, request):
        if request.mode == ReplayMode.RECORDED_CONFIGURATION:
            if request.input_source != "navigation_journal":
                raise ValueError("recorded_navigation_journal_required")
            if request.process_model_revision is not None or request.quality_policy_revision is not None:
                raise ValueError("navigation_revision_override_unsupported")
            available=self.ConfigurationAvailability_Get(dataset)
            if not available.recorded_available:
                raise ValueError("recorded_configuration_unavailable:"+",".join(available.missing_recorded_parameters))
            if request.parameters and dict(request.parameters)!={"configuration_json":""}:
                raise ValueError("recorded_configuration_override_forbidden")
            return {"configuration_json":""}
        if request.process_model_revision is not None or request.quality_policy_revision is not None:
            raise ValueError("navigation_revision_override_unsupported")
        if request.input_source != "corrected_imu":
            raise ValueError("corrected_imu_required")
        self.metadata.Parameters_Validate(request.parameters)
        _Configuration_Read(self.model, request.parameters["configuration_json"])
        if ("configuration_origin" in _Json_Read(request.parameters["configuration_json"])
                and request.mode != ReplayMode.WHAT_IF):
            raise ValueError("scg_conversion_requires_what_if")
        if ("body_input_assumption" in _Json_Read(request.parameters["configuration_json"])
                and request.mode != ReplayMode.WHAT_IF):
            raise ValueError("navigation_body_assumption_requires_what_if")
        configuration = _Json_Read(request.parameters["configuration_json"])
        if "configuration_origin" in configuration:
            from .firmware_configuration import ConfigurationDataset_Validate
            ConfigurationDataset_Validate(dataset, configuration)
        return dict(request.parameters)

    def ParameterAudit_Get(self, dataset, request):
        if request.mode == ReplayMode.RECORDED_CONFIGURATION:
            from .recorded_journal import RecordedJournal_Read,SCHEMA
            journal=RecordedJournal_Read(dataset,self.model)
            return {"config_mode":request.mode.value,"config_source":"Recorded operation journal and exact .ssdecoder actual parameters",
                "parameter_schema_identity":self.metadata.ParameterSchemaIdentity_Get(),
                "firmware_build_parameters":{p["id"]:p["value"] for p in journal.parameter_group["parameters"]},
                "parameter_metadata":{p.parameter_id:p.ToDict() for p in self.metadata.firmware_only_parameter_schema},
                "journal_schema":SCHEMA.rsplit("/",1)[0]+"/"+str(journal.revision),"journal_sha256":journal.sha256,"journal_epoch":journal.epoch,
                "source_parameter_group":journal.parameter_group}
        from .firmware_configuration import ConfigurationOriginAudit_Get, ConfigurationOrigin_Validate
        origin_audit = {}
        try:
            configuration = _Json_Read(request.parameters.get("configuration_json", ""))
            if isinstance(configuration, dict) and "configuration_origin" in configuration:
                ConfigurationOrigin_Validate(self.model, configuration)
                origin_audit = ConfigurationOriginAudit_Get(configuration)
        except (ValueError, TypeError, KeyError):
            pass  # An unexecuted editor draft may be incomplete; run() validates it.
        return {**origin_audit,"config_mode": request.mode.value, "config_source": CONFIG_SOURCE,
            "parameter_schema_identity": self.metadata.ParameterSchemaIdentity_Get(),
            "firmware_build_parameters": {},
            "parameter_metadata": {spec.parameter_id: spec.ToDict() for spec in self.metadata.parameter_schema}}

    def run(self, dataset, request, context=None):
        from silverstar_flp.core.runtime import NumericalRuntime_Validate
        NumericalRuntime_Validate()
        context = context or TaskContext()
        parameters = self.Parameters_Resolve(dataset, request)
        if request.mode == ReplayMode.RECORDED_CONFIGURATION:
            from .recorded_journal import RecordedJournal_Read,RecordedJournal_Execute
            journal=RecordedJournal_Read(dataset,self.model)
            times,states,outcomes=RecordedJournal_Execute(journal,context)
            bounds=MissionReplayBounds_Get(dataset,source_end_timestamp_us=times[-1])
            selected=[(t,state) for t,state in zip(times,states) if bounds.start_timestamp_us<=t<=bounds.end_timestamp_us]
            if not selected:
                raise ValueError("navigation_journal_no_mission_output")
            times,states=map(list,zip(*selected))
            provenance="Derived/recorded operation journal"
            diagnostics={**self.ParameterAudit_Get(dataset,request),
                "input_contract":{"reader":"NAVIGATION_OPERATION_PART/v1","complete_sealed_epoch":True,"operation_revision":journal.revision,
                    "operations":len(journal.operations),"immutable_log":True},
                "firmware_equivalence":"NOT_PROVEN","arithmetic":"float64", "data_provenance":provenance,
                "measurement_outcomes":outcomes,"numerical_fidelity":"host model; no target golden qualification"}
            return AlgorithmResult(self.metadata.plugin_id,VERSION,"navigation_journal",parameters,
                ReplayFidelity.APPROXIMATE,(),("recorded_inputs_no_target_golden",),
                self._Channels_Build(times,states,provenance),diagnostics,"Recomputed")
        state, gravity, density, records = _Configuration_Read(self.model, parameters["configuration_json"])
        observations, identities = _Observations_Build(self.model, records, request)
        steps, audit = _BodyInputs_Get(dataset, _Json_Read(parameters["configuration_json"]).get("body_input_assumption"))
        if request.mode == ReplayMode.OFFLINE:
            recorded_q = np.asarray(dataset.initial_state.payload["q_nb"], dtype=float)
            rotation = Rotation.from_quat(recorded_q, scalar_first=True).as_matrix()
            nominal_r = state.rotation if self.model == "eskf20" else state.group[:3, :3]
            if not np.allclose(rotation, nominal_r, rtol=0, atol=1e-7):
                raise ValueError("navigation_initial_attitude_change_requires_what_if")
        session = BufferedSession(self.model, state, steps[0].start_us, identities, gravity, density)
        histories, times, outcomes = [state], [session.state_us], []
        pending = list(observations)
        for index, step in enumerate(steps):
            context.Cancel_RaiseIfRequested()
            end = step.end_us
            if session.predict_pair(step.start_us, end, [step.gyro1, step.gyro2],
                    [step.accel1, step.accel2], gravity, density) != Result.OK:
                raise ValueError("navigation_prediction_failed")
            due = [(row, event) for row, event in pending if row["receive_us"] <= end]
            pending = [(row, event) for row, event in pending if row["receive_us"] > end]
            for row, event in due:
                if row["kind"] == "magnetic":
                    result = session.update_magnetic(event, row["value"], row["covariance"], row["stage"],
                        row["hard_iron_uT"], row["soft_iron"], row["reference_strength_uT"],
                        row["ratio_bounds"], row["gate"])
                else:
                    result = session.update_vector(event, row["kind"], row["value"], row["covariance"], row["gate"])
                outcomes.append({"kind": row["kind"], "sample_us": event.sample_us,
                    "receive_us": event.receive_us, "evaluation_us": end,
                    "result": result_label(result),
                    "provenance": "user_configuration", "time_basis": row["time_basis"]})
            histories.append(session.state); times.append(end)
            context.Progress_Report((index + 1) / len(steps), "navigation_reference.replay")
        for row, event in pending:
            outcomes.append({"kind": row["kind"], "sample_us": event.sample_us,
                "receive_us": event.receive_us, "result": "after_replay_end",
                "provenance": "user_configuration", "time_basis": row["time_basis"]})
        diagnostics = {**self.ParameterAudit_Get(dataset, request), "input_contract": audit,
            "output_row_to_input_interval": [{"row": i + 1, "start_us": s.start_us,
                "end_us": s.end_us, "source_id": s.source, "reader_generation": s.generation}
                for i, s in enumerate(steps)],
            "output_sampling": "initial state, then one row per complete input pair at original end_us",
            "implementation_id": f"{self.model}/{VERSION}", "arithmetic": "float64",
            "firmware_equivalence": "NOT_PROVEN", "data_provenance": "Derived/user configuration",
            "vector_observation_contract": "IMU-origin ENU position m / velocity m/s; user supplied; no lever-arm correction",
            "measurement_outcomes": outcomes, "magnetic_observation_count": sum(r["kind"] == "magnetic" for r in records),
            "recorded_gnss_admission": "unavailable: per-instance IMU-origin geometry and time contract not bound",
            "recorded_magnetic_admission": "unavailable: MAG_NATIVE is not hard-soft-only calibrated provenance",
            "model_source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in Path(__file__).parent.glob("*.py")}}
        warnings = ["host_reference_no_firmware_parity", "derived_explicit_configuration"]
        if self.model != "inekf15" and not diagnostics["magnetic_observation_count"]:
            warnings.append("magnetic_no_observation_full_covariance_retained")
        return AlgorithmResult(self.metadata.plugin_id, VERSION, request.input_source, parameters,
            ReplayFidelity.APPROXIMATE, (), tuple(warnings), self._Channels_Build(times, histories),
            diagnostics, "What-if" if request.mode == ReplayMode.WHAT_IF else "Offline")

    def _Channels_Build(self, timestamps, states, provenance="Derived/user configuration"):
        def values(state):
            if self.model == "eskf20":
                return state.rotation, state.velocity, state.position
            return state.group[:3, :3], state.group[:3, 3], state.group[:3, 4]
        navigation = [values(state) for state in states]
        quaternions = [Rotation.from_matrix(row[0]).as_quat(scalar_first=True) for row in navigation]
        for index in range(1, len(quaternions)):
            if np.dot(quaternions[index - 1], quaternions[index]) < 0:
                quaternions[index] *= -1
        def series(rows, unit, quantity, columns=()):
            return TimeSeries(np.asarray(timestamps, dtype=np.uint64), np.asarray(rows), unit, quantity,
                self.metadata.plugin_id, np.ones(len(timestamps), dtype=bool), columns,
                {"provenance": provenance, "implementation_id": VERSION})
        size = _MODELS[self.model][1]
        output = {"attitude.q_nb": series(quaternions, "1", "quaternion", ("W", "X", "Y", "Z")),
            "navigation.velocity_enu": series([row[1] for row in navigation], "m/s", "velocity", ("E", "N", "U")),
            "navigation.position_enu": series([row[2] for row in navigation], "m", "position", ("E", "N", "U")),
            f"{self.model}.covariance.diagonal": series([np.diag(s.covariance) for s in states], "mixed", "covariance"),
            f"{self.model}.covariance.upper_triangle": series([s.covariance[np.triu_indices(size)] for s in states], "mixed", "covariance"),
            f"{self.model}.gyro_bias": series([s.gyro_bias for s in states], "rad/s", "bias"),
            f"{self.model}.accel_bias": series([s.accel_bias for s in states], "m/s^2", "bias")}
        return output


class Eskf20AlgorithmPlugin(NavigationReferenceAlgorithmPlugin):
    def __init__(self):
        super().__init__("eskf20")


class InEkf15AlgorithmPlugin(NavigationReferenceAlgorithmPlugin):
    def __init__(self):
        super().__init__("inekf15")


class InEkf20AlgorithmPlugin(NavigationReferenceAlgorithmPlugin):
    def __init__(self):
        super().__init__("inekf20")
