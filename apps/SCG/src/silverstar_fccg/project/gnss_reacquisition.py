"""Explicit actual configuration for the experimental ESKF recovery capability."""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass

OWNER = "silverstar.algorithm.estimator.eskf15"
VERSION = "0.4.0"
SCHEMA_ID = "silverstar.navigation.gnss_reacquisition"
CAPABILITY = {
    "schema_id": SCHEMA_ID,
    "revision": 1,
    "enabled_parameter": "gnss_recovery_enabled",
}
CAPS = tuple(
    "cap_" + name
    for name in (
        "position_e",
        "position_n",
        "position_u",
        "velocity_e",
        "velocity_n",
        "velocity_u",
        "theta_x",
        "theta_y",
        "theta_z",
        "gyro_bias_x",
        "gyro_bias_y",
        "gyro_bias_z",
        "accel_bias_x",
        "accel_bias_y",
        "accel_bias_z",
    )
)
DURATIONS = ("loss_gap_ms", "stable_span_ms", "maximum_interval_ms", "cooldown_ms")
COUNTS = ("stable_count", "reject_count", "confirmation_count", "maximum_attempts")
FIELDS = (
    "enabled",
    *DURATIONS,
    *COUNTS,
    "uniform_scale",
    *CAPS,
    "clock_jitter_ms",
    "horizontal_acceleration_limit_mps2",
    "vertical_acceleration_limit_mps2",
    "closure_sigma",
)
WIRE = struct.Struct("<I4I4B16fI3f")


@dataclass(frozen=True, slots=True)
class GnssReacquisitionConfiguration:
    enabled: bool
    identity: int
    wire: bytes
    values: tuple[tuple[str, int | float], ...]


def GnssReacquisitionConfiguration_Resolve(parameters):
    """Zero placeholders cannot enable recovery; actual binary32 values are bound."""
    missing = [name for name in FIELDS if "gnss_recovery_" + name not in parameters]
    if missing:
        raise ValueError(
            "GNSS recovery actual parameters missing: " + ", ".join(missing)
        )
    values = {}
    integer_names = {"enabled", *DURATIONS, *COUNTS, "clock_jitter_ms"}
    for name in FIELDS:
        value = parameters["gnss_recovery_" + name]
        if name in integer_names:
            maximum = (
                1
                if name == "enabled"
                else (
                    255
                    if name in COUNTS
                    else (
                        500
                        if name in ("maximum_interval_ms", "clock_jitter_ms")
                        else 2**31 - 1
                    )
                )
            )
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError("Invalid GNSS recovery integer: " + name)
        else:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid GNSS recovery float: " + name)
            try:
                value = struct.unpack("<f", struct.pack("<f", value))[0]
            except (OverflowError, struct.error) as error:
                raise ValueError(
                    "Unrepresentable GNSS recovery float: " + name
                ) from error
            if not math.isfinite(value) or (name == "uniform_scale" and value > 2):
                raise ValueError("Invalid GNSS recovery binary32: " + name)
        values[name] = value
    if values["enabled"]:
        positive = (
            *DURATIONS,
            *COUNTS,
            "uniform_scale",
            *CAPS,
            "horizontal_acceleration_limit_mps2",
            "vertical_acceleration_limit_mps2",
            "closure_sigma",
        )
        if any(values[name] <= 0 for name in positive) or values["stable_count"] < 2:
            raise ValueError(
                "Active GNSS recovery requires a complete explicit positive configuration"
            )
        if (
            values["loss_gap_ms"] <= values["maximum_interval_ms"]
            or values["clock_jitter_ms"] > values["maximum_interval_ms"]
            or values["uniform_scale"] <= 1
        ):
            raise ValueError(
                "Active GNSS recovery interval/jitter/scale constraints failed"
            )
    wire = WIRE.pack(*(values[name] for name in FIELDS))
    return GnssReacquisitionConfiguration(
        bool(values["enabled"]),
        zlib.crc32(wire) or 0xFFFFFFFF,
        wire,
        tuple(values.items()),
    )


def GnssReacquisitionMetadata_Validate(owner, values):
    declaration = owner.metadata.get("gnss_reacquisition_contract")
    if (
        declaration != CAPABILITY
        or owner.component_id != OWNER
        or owner.version != VERSION
    ):
        raise ValueError("GNSS recovery component/capability identity is unsupported")
    return GnssReacquisitionConfiguration_Resolve(values)


def GnssReacquisitionActivation_Validate(model, catalog):
    """Product activation remains closed until the complete evidence is reviewed.

    Pure configuration/kernel tests may still validate explicit synthetic policy;
    this never authorizes an enabled generated firmware or Recorded declaration.
    """
    owner = model.strategies.get("estimator")
    if owner is None:
        return
    manifest = catalog.Component_Get(owner)
    if "gnss_reacquisition_contract" not in manifest.metadata:
        return
    config = GnssReacquisitionMetadata_Validate(manifest, model.algorithm_parameters.get(owner, {}))
    if config.enabled:
        raise ValueError("Active GNSS reacquisition is blocked: end-to-end acceptance evidence is incomplete; keep gnss_recovery_enabled=0")


def GnssReacquisitionDeclaration_Get(model, catalog):
    owner = model.strategies.get("estimator")
    if owner is None:
        return None
    manifest = catalog.Component_Get(owner)
    if "gnss_reacquisition_contract" not in manifest.metadata:
        return None
    GnssReacquisitionActivation_Validate(model, catalog)
    from silverstar_fccg.generator.fusion_timing import FusionTimingDeclaration_Get

    if FusionTimingDeclaration_Get(model, catalog) is None:
        raise ValueError(
            "GNSS recovery requires proven owning timing/source provenance"
        )
    from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve

    actual = next(
        row
        for row in AlgorithmParameters_Resolve(model, catalog)
        if row["component"] == owner
    )
    config = GnssReacquisitionMetadata_Validate(
        manifest, {row["id"]: row["value"] for row in actual["parameters"]}
    )
    return {
        "schema_id": SCHEMA_ID,
        "revision": 1,
        "component": OWNER,
        "component_version": VERSION,
        "enabled": config.enabled,
        "configuration_id": config.identity,
        "configuration_wire_hex": config.wire.hex(),
    }
