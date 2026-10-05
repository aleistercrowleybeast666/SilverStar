"""Validate the configured CubeMX HCLK against the selected exact MCU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ClockPlanIssue:
    code: str
    message: str


def ClockPlan_Validate(
    inventory: dict[str, Any], exact_metadata: dict[str, Any],
) -> tuple[ClockPlanIssue, ...]:
    clocks = inventory.get("clocks", {})
    hclk = clocks.get("RCC.HCLKFreq_Value") if isinstance(clocks, dict) else None
    if type(hclk) is not int or hclk <= 0:
        return (ClockPlanIssue(
            "HCLK_UNDECLARED", "Hardware inventory has no positive CubeMX HCLK",
        ),)
    maximum = exact_metadata.get("max_hclk_hz")
    if type(maximum) is not int or maximum <= 0:
        return (ClockPlanIssue(
            "MCU_HCLK_LIMIT_UNDECLARED", "Exact MCU has no HCLK limit",
        ),)
    if hclk > maximum:
        return (ClockPlanIssue(
            "HCLK_EXCEEDS_MCU_LIMIT",
            f"Configured HCLK {hclk} Hz exceeds exact MCU limit {maximum} Hz",
        ),)
    return ()
