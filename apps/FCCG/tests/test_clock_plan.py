from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.clock_plan import ClockPlan_Validate
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from test_f103_ground_reference import _GroundF103Model_Get


def test_exact_mcu_hclk_limits_use_actual_inventory(builtin_catalog) -> None:
    flight = ReferenceProject_Create("FlightClock", catalog=builtin_catalog)
    exact = builtin_catalog.Component_Get(flight.mcu)
    assert not ClockPlan_Validate(flight.hardware.inventory, exact.metadata)
    inventory = deepcopy(flight.hardware.inventory)
    inventory["clocks"]["RCC.HCLKFreq_Value"] = 169_000_000
    flight.hardware = replace(flight.hardware, inventory=inventory)
    assert "HCLK_EXCEEDS_MCU_LIMIT" in {
        issue.code for issue in Project_Validate(flight, builtin_catalog).issues
    }

    ground = _GroundF103Model_Get(builtin_catalog)
    assert not GroundTargetIssues_Get(ground, builtin_catalog)
    inventory = deepcopy(ground.ground_target.hardware.inventory)
    inventory["clocks"]["RCC.HCLKFreq_Value"] = 73_000_000
    ground.ground_target = replace(
        ground.ground_target,
        hardware=replace(ground.ground_target.hardware, inventory=inventory),
    )
    assert "GROUND_HCLK_EXCEEDS_MCU_LIMIT" in {
        issue.code for issue in GroundTargetIssues_Get(ground, builtin_catalog)
    }


def test_missing_hclk_is_not_treated_as_zero_workload() -> None:
    assert ClockPlan_Validate({}, {"max_hclk_hz": 72_000_000})[0].code == (
        "HCLK_UNDECLARED"
    )
