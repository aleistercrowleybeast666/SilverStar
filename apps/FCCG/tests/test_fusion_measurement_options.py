from __future__ import annotations

from dataclasses import replace

import pytest
import re

from silverstar_fccg.generator.render import _FlightConfigHeader_Render
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Reconcile
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
from silverstar_fccg.project.configuration import StrategyAvailabilities_Get
from silverstar_fccg.project.reference import ReferenceProject_Create


_ESTIMATORS = (
    "silverstar.algorithm.estimator.sf6",
    "silverstar.algorithm.estimator.kf6",
)


def _Project_Create(catalog, observations: str):
    model = ReferenceProject_Create(catalog=catalog)
    if observations in {"gnss", "none"}:
        model.device_instances[0] = replace(
            model.device_instances[0],
            interface="uart", profile="jy901s",
        )
        model.strategies["landing"] = "silverstar.flight_logic.landing.stillness"
    if observations in {"baro", "none"}:
        model.device_instances = [instance for instance in model.device_instances
                                  if instance.instance_id != "gnss0"]
    return model


@pytest.mark.parametrize("estimator", _ESTIMATORS)
@pytest.mark.parametrize("observations,expected,mask", (
    ("both", {"gnss.position", "gnss.velocity", "barometer.altitude"}, "0x1FU"),
    ("gnss", {"gnss.position", "gnss.velocity"}, "0x0FU"),
    ("baro", {"barometer.altitude"}, "0x10U"),
    ("none", set(), "0x00U"),
))
def test_estimator_requires_one_configured_measurement(
    builtin_catalog, estimator: str, observations: str,
    expected: set[str], mask: str,
) -> None:
    model = _Project_Create(builtin_catalog, observations)
    model.strategies["estimator"] = estimator
    AlgorithmParameters_Reconcile(model, builtin_catalog)
    LoggingProfile_Reconcile(model, builtin_catalog)
    resolution = CapabilityResolution_Resolve(model, builtin_catalog)
    required = {use.capability for use in resolution.requirements
                if use.consumer_component == estimator}
    assert required.intersection(
        {"gnss.position", "gnss.velocity", "barometer.altitude"}
    ) == expected
    availability = StrategyAvailabilities_Get(model, builtin_catalog)[estimator]
    assert availability.available == bool(expected)
    assert Project_Validate(model, builtin_catalog).valid == bool(expected)
    assert ("fusion.measurement" in required) == (not expected)
    header = _FlightConfigHeader_Render(model, builtin_catalog.ProjectView_Get(model))
    assert re.search(r"#define\s+SYSTEM_FUSION_CONFIGURED_MASK\s+" + mask, header)
    required = re.search(r"#define\s+SYSTEM_USER_ALIGNMENT_REQUIRED_MASK\s+([^\n]+)", header)
    assert required is not None
    if observations == "gnss":
        assert "SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN" in required.group(1)
        assert "SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN" not in required.group(1)
    elif observations in {"both", "baro"}:
        assert "SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN" in required.group(1)


@pytest.mark.parametrize("observations,available", (
    ("both", True), ("gnss", False), ("baro", False), ("none", False),
))
def test_eskf15_keeps_existing_source_contract(
    builtin_catalog, observations: str, available: bool,
) -> None:
    model = _Project_Create(builtin_catalog, observations)
    estimator = "silverstar.algorithm.estimator.eskf15"
    model.strategies["estimator"] = estimator
    assert StrategyAvailabilities_Get(model, builtin_catalog)[estimator].available == available


@pytest.mark.parametrize("profile", ("raw_200_hz", "bosch_sync_400_hz"))
def test_bmi088_i2c_flight_capabilities(builtin_catalog, profile: str) -> None:
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances[0] = replace(
        model.device_instances[0], plugin="silverstar.device.imu.bmi088",
        interface="i2c", profile=profile,
    )
    capabilities = set(builtin_catalog.ProjectView_Get(model).InstanceComponent_Get(
        model.device_instances[0]).provides)
    assert {"imu.software_alignment_qualified", "imu.software_propagation_qualified",
            "imu.landing_stillness_qualified"} <= capabilities
    assert "imu.landing_impact_qualified" not in capabilities


@pytest.mark.parametrize("nose_axis", (
    "x_positive", "x_negative", "y_positive", "y_negative",
    "z_positive", "z_negative",
))
def test_raw_imu_mount_is_right_handed_and_serialized(
    builtin_catalog, nose_axis: str,
) -> None:
    from silverstar_fccg.project.model import (
        ProjectModel_Parse, RAW_IMU_NOSE_AXIS_MAPS,
    )
    from silverstar_fccg.generator.render import _InstanceResourceDeclarations_Render

    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances[0] = replace(
        model.device_instances[0], plugin="silverstar.device.imu.bmi088",
        interface="i2c", profile="raw_200_hz", mount_nose_axis=nose_axis,
    )
    axis_map = RAW_IMU_NOSE_AXIS_MAPS[nose_axis]
    source_axis = {"x": 1, "y": 2, "z": 3}[nose_axis[0]]
    expected_sign = 1 if nose_axis.endswith("positive") else -1
    assert axis_map[2] == source_axis * expected_sign
    first, second, third = axis_map
    permutation = [abs(first), abs(second), abs(third)]
    inversions = sum(permutation[i] > permutation[j]
                     for i in range(3) for j in range(i + 1, 3))
    assert ((-1) ** inversions) * first * second * third > 0
    encoded = model.Dictionary_Get()
    assert encoded["components"]["devices"][0]["mount_nose_axis"] == nose_axis
    assert ProjectModel_Parse(encoded).device_instances[0].mount_nose_axis == nose_axis
    declaration = _InstanceResourceDeclarations_Render(
        model, builtin_catalog.ProjectView_Get(model))
    assert "int8_t axis_map[3];" in declaration
