"""Ephemeral KF6 diagnostics; never part of parameter or project schemas."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from silverstar_flp.plugins.api.algorithm import ReplayRequest


@dataclass(frozen=True, slots=True)
class Kf6DiagnosticOptions:
    velocity_shift_ms: int = 0
    baro_effective_sigma_m: float | None = None
    gnss_position_vertical_disabled: bool = False

    def __post_init__(self):
        if type(self.velocity_shift_ms) is not int or not -500 <= self.velocity_shift_ms <= 500:
            raise ValueError("velocity_shift_out_of_range")
        sigma = self.baro_effective_sigma_m
        if sigma is not None and (
            isinstance(sigma, bool) or not math.isfinite(sigma) or not 1.5 <= sigma <= 100
        ):
            raise ValueError("baro_effective_sigma_out_of_range")
        if type(self.gnss_position_vertical_disabled) is not bool:
            raise ValueError("gnss_position_vertical_disabled_invalid")


@dataclass(frozen=True, slots=True)
class Kf6DiagnosticRequest:
    replay: ReplayRequest
    options: Kf6DiagnosticOptions | None = None
    operation: str = "replay"


def DiagnosticSchedule_Apply(schedule, options):
    if options is None or options.baro_effective_sigma_m is None:
        return schedule
    return tuple(
        replace(
            item,
            record=replace(
                item.record,
                payload={
                    **item.record.payload,
                    "variance_m2": options.baro_effective_sigma_m**2,
                },
            ),
        )
        if item.kind == "baro"
        else item
        for item in schedule
    )


def Distribution_Get(values):
    data = np.asarray(values, dtype=float).reshape(-1)
    data = data[np.isfinite(data)]
    if not len(data):
        return None
    return {
        "min": float(min(data)),
        "median": float(np.median(data)),
        "max": float(max(data)),
        "count": len(data),
    }


def MeasurementWeights_Inspect(dataset, parameters, firmware_schedule, analysis_schedule, options):
    """Report input R before NIS soft weighting, including origin contribution."""
    initial = dataset.initial_state.payload
    native = {}
    for kind, role in (
        ("GNSS_NATIVE", "canonical:gnss.position"),
        ("BARO_NATIVE", "canonical:barometer.altitude"),
    ):
        context = dataset.semantic_context
        route = context.CanonicalRoute_Get(role) if context else None
        ids = tuple(route.get("endpoint_descriptor_ids", ())) if route else ()
        if len(ids) != 1:
            native[kind] = ()
            continue
        endpoint = context.CapabilityEndpoint_Get(ids[0])
        native[kind] = tuple(
            r
            for r in dataset.Records_Get(kind)
            if r.payload.get("source_descriptor_id") == ids[0]
            and r.payload.get("instance_id") == endpoint.get("instance_id")
        )
    groups = []
    specs = (
        (
            "position_EN",
            "gnss",
            "position_variance_m2",
            (0, 1),
            "gnss_position_std_horizontal",
            "horizontal_accuracy_m",
            1.25,
        ),
        (
            "position_U",
            "gnss",
            "position_variance_m2",
            (2,),
            "gnss_position_std_vertical",
            "vertical_accuracy_m",
            1.25,
        ),
        (
            "velocity_EN",
            "gnss",
            "velocity_variance_m2ps2",
            (0, 1),
            "gnss_velocity_std",
            "velocity_variance_m2ps2",
            1.25,
        ),
        (
            "velocity_U",
            "gnss",
            "velocity_variance_m2ps2",
            (2,),
            "gnss_velocity_std",
            "velocity_variance_m2ps2",
            1.25,
        ),
        ("baro_U", "baro", "variance_m2", (), "baro_std_m", "altitude_variance_m2", 1),
    )
    for group, kind, field, axes, configured, native_field, receiver_scale in specs:

        def variances(schedule, field=field, axes=axes, kind=kind):
            return [
                np.asarray(item.record.payload[field])[list(axes)]
                if axes
                else item.record.payload[field]
                for item in schedule
                if item.kind == kind
            ]

        fw = np.asarray(variances(firmware_schedule))
        actual = np.asarray(variances(analysis_schedule))
        raws = []
        for record in native["GNSS_NATIVE" if kind == "gnss" else "BARO_NATIVE"]:
            value = np.asarray(record.payload.get(native_field, np.nan))
            if "variance" in native_field:
                value = np.sqrt(np.maximum(value, 0))
            if value.ndim and axes:
                value = value[list(axes)]
            raws.extend(np.asarray(value).reshape(-1).tolist())
        origin = (
            np.asarray(initial.get("gnss_origin_position_std_m", (0, 0, 0)))[list(axes)] ** 2
            if group.startswith("position")
            else np.asarray([initial.get("barometer_origin_std_m", 0) ** 2])
            if kind == "baro"
            else np.asarray([0])
        )
        disabled = bool(
            options and options.gnss_position_vertical_disabled and group == "position_U"
        )
        groups.append(
            {
                "group": group,
                "configured_sigma": parameters[configured],
                "native_sigma": Distribution_Get(raws),
                "receiver_scale": receiver_scale,
                "vertical_scale": parameters.get("gnss_velocity_vertical_scale", 1)
                if group == "velocity_U"
                else 1,
                "origin_variance": Distribution_Get(origin),
                "firmware_effective_sigma": Distribution_Get(np.sqrt(fw)),
                "firmware_R": Distribution_Get(fw),
                "effective_sigma": None if disabled else Distribution_Get(np.sqrt(actual)),
                "effective_R": None if disabled else Distribution_Get(actual),
                "disabled": disabled,
                "rule": "disabled"
                if disabled
                else "analysis_exact_sigma_squared"
                if kind == "baro" and options and options.baro_effective_sigma_m is not None
                else "baro_max_plus_origin"
                if kind == "baro"
                else "gnss_max_scale_plus_origin",
                "sample_dependent": True,
                "R_stage": "input_before_NIS_soft_weighting",
            }
        )
    return groups


def DiagnosticMetadata_Get(dataset, parameters, options, weights):
    descriptor = dataset.Records_Get("DECODER_PROFILE_DESCRIPTOR")
    return {
        "mode": "analysis_only" if options is not None else "firmware_faithful",
        "log": str(dataset.source_path),
        "decoder_identity": dict(descriptor[0].payload) if descriptor else None,
        "firmware_parameters": dict(parameters),
        "analysis_only_overrides": asdict(options) if options is not None else {},
        "measurement_weights": weights,
        "initialization": "recorded_initial_state_frozen" if options else "production_resolver",
        "timing_method": "velocity_and_receiver_variance_resampling; positive_delays",
    }


def DiagnosticResult_Export(path: Path, result_metadata: dict, scan: dict | None = None):
    payload = {"diagnostic_result": result_metadata, "latency_scan": scan}
    # Exclusive creation prevents accidental replacement of a source or earlier report.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
