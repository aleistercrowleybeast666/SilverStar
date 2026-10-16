"""Nominal configured-rate capacity proof for the bounded delayed primary.

This is a static queue sizing check. It does not establish MCU execution time,
ISR scheduling, source switching bursts or any hardware qualification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FusionHorizonRateIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class FusionHorizonRatePlan:
    horizon_us: int
    numerical_revision: int
    body_capacity: int
    event_capacity: int
    maximum_work: int
    required_body_slots: int
    required_event_slots: int
    producer_rates: tuple[tuple[str, int, int], ...]
    issues: tuple[FusionHorizonRateIssue, ...]


def FusionHorizonRatePlan_Build(model, catalog, values, propagation_hz):
    """Use physical providers and already resolved estimator parameter values."""
    from silverstar_fccg.generator.render import _DeviceDescriptorEntries_Get

    owner = model.strategies.get("estimator")
    revisions = {
        "silverstar.algorithm.estimator.kf6": (1, 512),
        "silverstar.algorithm.estimator.eskf15": (2, 832),
    }
    if owner not in revisions:
        raise ValueError("Delayed primary requires an owning KF6 or ESKF15 backend")
    lag = values.get("fusion_horizon_ms")
    if type(lag) is not int or not 10 <= lag <= 550:
        raise ValueError(
            "Delayed primary lag must be an actual integer in [10, 550] ms"
        )
    if (
        isinstance(propagation_hz, bool)
        or not isinstance(propagation_hz, (int, float))
        or not math.isfinite(propagation_hz)
        or propagation_hz <= 0
    ):
        raise ValueError("Delayed primary requires a finite positive propagation rate")
    issues = []
    delay = max(
        (
            value
            for key, value in values.items()
            if key.endswith("_measurement_delay_ms")
        ),
        default=0,
    )
    if lag < delay:
        issues.append(
            FusionHorizonRateIssue(
                "FUSION_HORIZON_DELAY_UNCOVERED",
                f"{lag} ms primary lag cannot cover the configured {delay} ms fallback measurement delay",
            )
        )
    catalog = catalog.ProjectView_Get(model)
    classes = {
        "SYSTEM_DEVICE_CLASS_GNSS": ("SYSTEM_GNSS_NAVIGATION_RATE_HZ", 4),
        "SYSTEM_DEVICE_CLASS_BAROMETER": ("SYSTEM_BAROMETER_OUTPUT_RATE_HZ", 1),
    }
    rates = []
    for entry in _DeviceDescriptorEntries_Get(model, catalog):
        device_class = entry.get("class")
        if device_class not in classes:
            continue
        source_id = str(entry["_source_instance_id"])
        manifest = (
            catalog.InstanceIdComponent_Get(source_id)
            if source_id
            else catalog.Component_Get(str(entry["_component_id"]))
        )
        symbol, groups = classes[device_class]
        rate = (
            manifest.metadata.get("runtime_defaults", {})
            .get(device_class, {})
            .get(symbol)
        )
        identity = source_id or manifest.component_id
        if type(rate) is not int or not 0 < rate <= 10000:
            issues.append(
                FusionHorizonRateIssue(
                    "FUSION_HORIZON_RATE_UNPROVEN",
                    f"{identity} has no bounded configured physical rate for {symbol}",
                )
            )
            continue
        rates.append((identity, rate, groups))
    # One endpoint/burst receipt per physical producer is retained in addition
    # to its nominal lag interval. Count all selectable providers conservatively.
    bodies = math.ceil(lag * propagation_hz / 1000) + 1
    events = sum(
        groups * (math.ceil(lag * rate / 1000) + 1) for _, rate, groups in rates
    )
    if bodies > 160:
        issues.append(
            FusionHorizonRateIssue(
                "FUSION_HORIZON_BODY_CAPACITY",
                f"{bodies} raw intervals required, fixed capacity is 160",
            )
        )
    if events > 64:
        issues.append(
            FusionHorizonRateIssue(
                "FUSION_HORIZON_EVENT_CAPACITY",
                f"{events} measurement slots required, fixed capacity is 64",
            )
        )
    numerical, work = revisions[owner]
    return FusionHorizonRatePlan(
        lag * 1000,
        numerical,
        160,
        64,
        work,
        bodies,
        events,
        tuple(rates),
        tuple(issues),
    )
