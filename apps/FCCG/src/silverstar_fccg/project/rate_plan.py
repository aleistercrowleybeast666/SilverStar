"""Static IMU propagation and fixed-lag replay contract for a Flight target."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel


@dataclass(frozen=True, slots=True)
class InertialRateIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class InertialRatePlan:
    raw_imu_odr_hz: int
    aggregation: int
    effective_propagation_rate_hz: float
    maximum_measurement_delay_ms: int
    maximum_replay_steps: int
    replay_window_ms: int
    required_history_steps: int
    history_capacity: int
    cpu_profile: str
    arithmetic_requirements: tuple[str, ...]
    issues: tuple[InertialRateIssue, ...]


def InertialRatePlan_Resolve(
    model: ProjectModel, catalog: PluginCatalog,
) -> InertialRatePlan:
    # Reuse the same primary physical-device route as generated firmware.
    from silverstar_fccg.generator.render import _DeviceRuntimeDefaults_Get

    defaults = dict(_DeviceRuntimeDefaults_Get(model, catalog))
    raw_rate = defaults.get("SYSTEM_IMU_OUTPUT_RATE_HZ", "")
    match = re.fullmatch(r"([1-9][0-9]*)U", raw_rate)
    if match is None:
        raise ValueError("Primary IMU has no finite declared output rate")
    odr_hz = int(match.group(1))
    ins_id = model.strategies.get("ins")
    aggregation = model.algorithm_parameters.get(ins_id or "", {}).get(
        "mechanization_aggregation", 2
    )
    if type(aggregation) is not int or aggregation not in (1, 2):
        raise ValueError("Mechanization aggregation must be one or two real samples")
    propagation_hz = odr_hz / aggregation
    estimator_id = model.strategies.get("estimator")
    estimator = catalog.Component_Get(estimator_id) if estimator_id else None
    delay_ms = 0
    window_ms = 0
    history_capacity = 0
    arithmetic: tuple[str, ...] = ()
    issues: list[InertialRateIssue] = []
    cpu_profile = str(catalog.Component_Get(model.mcu).metadata.get("cpu_profile", ""))
    if estimator is not None:
        values = model.algorithm_parameters.get(estimator_id, {})
        delay_ms = max(
            (int(value) for key, value in values.items()
             if key.endswith("_measurement_delay_ms")),
            default=0,
        )
        contract = estimator.metadata.get("replay_contract", {})
        if not isinstance(contract, dict):
            raise ValueError("Estimator replay contract must be an object")
        window_ms = int(contract.get("window_ms", 0))
        history_capacity = int(contract.get("history_capacity", 0))
        arithmetic = tuple(estimator.metadata.get("arithmetic_requirements", ()))
        qualified = estimator.metadata.get("qualified_timing_profiles", ())
        if cpu_profile not in qualified:
            issues.append(InertialRateIssue(
                "TIMING_PROFILE_UNQUALIFIED",
                f"{estimator.component_id} has no qualified timing profile for {cpu_profile}",
            ))
        if window_ms < delay_ms or history_capacity <= 0:
            issues.append(InertialRateIssue(
                "REPLAY_CONTRACT_INVALID",
                "Estimator history window or capacity cannot cover configured delay",
            ))
    required_history = math.ceil(window_ms * propagation_hz / 1000) + (
        1 if window_ms else 0
    )
    if history_capacity and required_history > history_capacity:
        issues.append(InertialRateIssue(
            "REPLAY_HISTORY_INSUFFICIENT",
            f"{required_history} inertial history slots are required at "
            f"{propagation_hz:g} Hz, but the estimator has {history_capacity}",
        ))
    maximum_replay_steps = math.ceil(delay_ms * propagation_hz / 1000)
    return InertialRatePlan(
        raw_imu_odr_hz=odr_hz,
        aggregation=aggregation,
        effective_propagation_rate_hz=propagation_hz,
        maximum_measurement_delay_ms=delay_ms,
        maximum_replay_steps=maximum_replay_steps,
        replay_window_ms=window_ms,
        required_history_steps=required_history,
        history_capacity=history_capacity,
        cpu_profile=cpu_profile,
        arithmetic_requirements=arithmetic,
        issues=tuple(issues),
    )
