"""Bounded project configuration for preflight attitude alignment."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

ALIGNMENT_MAX_CONSTRAINTS = 6
BODY_AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
RETIRED_ALIGNMENT_STRATEGIES = frozenset({
    "silverstar.algorithm.alignment.gravity_known_yaw",
    "silverstar.algorithm.alignment.gravity_mag_triad",
    "silverstar.algorithm.alignment.hardware_quat_6axis_known_yaw",
    "silverstar.algorithm.alignment.hardware_quat_9axis",
})


@dataclass(frozen=True, slots=True)
class AlignmentConstraint:
    kind: str
    weight: float = 1.0
    declination_deg: float = 0.0
    body_axis: str = "+X"
    nav_azimuth_deg: float = 90.0


@dataclass(frozen=True, slots=True)
class AlignmentConfiguration:
    constraints: tuple[AlignmentConstraint, ...] = (
        AlignmentConstraint("gravity"),
        AlignmentConstraint("reference_direction"),
    )
    external_source_instance: str = ""
    external_yaw_authoritative: bool = False
    external_known_azimuth_deg: float | None = 90.0

    def Dictionary_Get(self) -> dict[str, Any]:
        return {
            "constraints": [asdict(item) for item in self.constraints],
            "external_source_instance": self.external_source_instance,
            "external_yaw_authoritative": self.external_yaw_authoritative,
            "external_known_azimuth_deg": self.external_known_azimuth_deg,
        }


def AlignmentConfiguration_Parse(value: Any) -> AlignmentConfiguration:
    if not isinstance(value, dict) or set(value) != {
        "constraints", "external_source_instance", "external_yaw_authoritative",
        "external_known_azimuth_deg",
    }:
        raise ValueError("alignment must contain only its defined fields")
    raw_constraints = value["constraints"]
    if not isinstance(raw_constraints, list) or not 2 <= len(raw_constraints) <= ALIGNMENT_MAX_CONSTRAINTS:
        raise ValueError("alignment requires two to six bounded constraints")
    constraints: list[AlignmentConstraint] = []
    for entry in raw_constraints:
        if not isinstance(entry, dict) or set(entry) != {
            "kind", "weight", "declination_deg", "body_axis", "nav_azimuth_deg",
        }:
            raise ValueError("alignment constraint fields are invalid")
        kind = entry["kind"]
        weight = entry["weight"]
        declination = entry["declination_deg"]
        axis = entry["body_axis"]
        azimuth = entry["nav_azimuth_deg"]
        if kind not in {"gravity", "magnetic_field", "reference_direction"}:
            raise ValueError("alignment constraint kind is invalid")
        if type(weight) not in {int, float} or not math.isfinite(weight) or not 0.01 <= weight <= 100.0:
            raise ValueError("alignment weight is outside the finite range")
        if type(declination) not in {int, float} or not math.isfinite(declination) or not -180.0 <= declination <= 180.0:
            raise ValueError("magnetic declination is outside the finite range")
        if axis not in BODY_AXES:
            raise ValueError("reference body axis is invalid")
        if type(azimuth) not in {int, float} or not math.isfinite(azimuth) or not 0.0 <= azimuth < 360.0:
            raise ValueError("reference azimuth is outside the finite range")
        constraints.append(AlignmentConstraint(kind, float(weight), float(declination), axis, float(azimuth)))
    kinds = [item.kind for item in constraints]
    if kinds.count("gravity") != 1 or kinds.count("magnetic_field") > 1:
        raise ValueError("alignment needs one gravity and at most one magnetic constraint")
    source = value["external_source_instance"]
    authoritative = value["external_yaw_authoritative"]
    known_azimuth = value["external_known_azimuth_deg"]
    if not isinstance(source, str) or len(source) > 64:
        raise ValueError("external attitude source instance is invalid")
    if type(authoritative) is not bool:
        raise ValueError("external yaw authority must be boolean")
    if known_azimuth is not None and (
        type(known_azimuth) not in {int, float}
        or not math.isfinite(known_azimuth)
        or not 0.0 <= known_azimuth < 360.0
    ):
        raise ValueError("external known azimuth is invalid")
    if not authoritative and known_azimuth is None:
        raise ValueError("non-authoritative external yaw requires a known azimuth")
    return AlignmentConfiguration(tuple(constraints), source, authoritative, None if known_azimuth is None else float(known_azimuth))
