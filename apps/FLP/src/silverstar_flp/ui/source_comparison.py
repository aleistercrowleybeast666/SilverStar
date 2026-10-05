"""Display-only comparison of published physical channels in one immutable task."""
from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

import numpy as np

from silverstar_flp.core.analysis_source import ChannelResolver
from silverstar_flp.core.dataset import TimeSeries


class ComparisonResult(StrEnum):
    AVAILABLE = ""
    UNAVAILABLE = "comparison.unavailable"
    SAME_SOURCE = "comparison.same_source"
    PRIMARY_MISSING = "comparison.primary_missing"
    SECONDARY_MISSING = "comparison.secondary_missing"
    INCOMPATIBLE = "comparison.incompatible"
    NO_OVERLAP = "comparison.no_overlap"


def ComparisonSeries_Get(
    primary: TimeSeries | None,
    secondary: TimeSeries | None,
    resolver: ChannelResolver,
    secondary_source_id: str | None,
) -> tuple[TimeSeries | None, ComparisonResult]:
    """Return real secondary samples within common coverage, without interpolation.

    Callers map diagnostic groups through plugin specs before invoking this check.
    Standard channel IDs and those specs supply the published component/frame
    contract for the builtins. Explicit per-series task/frame/origin evidence must
    agree; it never gets overwritten by that default contract.
    """
    if secondary_source_id is None:
        return None, ComparisonResult.AVAILABLE
    first = resolver.Source_Get()
    second = resolver.Source_Get(secondary_source_id)
    if not first.available or not second.available:
        return None, ComparisonResult.UNAVAILABLE
    if first.source_id == second.source_id:
        return None, ComparisonResult.SAME_SOURCE
    if primary is None or primary.count == 0:
        return None, ComparisonResult.PRIMARY_MISSING
    if secondary is None or secondary.count == 0:
        return None, ComparisonResult.SECONDARY_MISSING
    known = set(resolver.store.RECORDED_ALGORITHMS.values())
    if first.algorithm_id not in known or second.algorithm_id not in known:
        return None, ComparisonResult.INCOMPATIBLE
    if (primary.quantity, primary.unit, primary.columns, primary.values.shape[1:]) != (
        secondary.quantity, secondary.unit, secondary.columns, secondary.values.shape[1:]
    ):
        return None, ComparisonResult.INCOMPATIBLE
    keys = ("frame", "coordinate_frame", "navigation_frame", "origin", "origin_enu",
            "origin_id", "mission_id", "task_id", "start_timestamp_us",
            "quaternion_convention", "reference_frame", "position_origin",
            "gnss_origin", "source_log_sha256", "log_sha256", "mission_start_us")
    for key in keys:
        if key in primary.metadata or key in secondary.metadata:
            if not np.array_equal(primary.metadata.get(key), secondary.metadata.get(key)):
                return None, ComparisonResult.INCOMPATIBLE
    first_finite = (np.isfinite(primary.values) if primary.values.ndim == 1
                    else np.all(np.isfinite(primary.values), axis=1))
    second_finite = (np.isfinite(secondary.values) if secondary.values.ndim == 1
                     else np.all(np.isfinite(secondary.values), axis=1))
    first_valid = np.flatnonzero(primary.valid & first_finite)
    second_mask = secondary.valid & second_finite
    second_valid = np.flatnonzero(second_mask)
    if not first_valid.size or not second_valid.size:
        return None, ComparisonResult.NO_OVERLAP
    start = max(primary.timestamp_us[first_valid[0]], secondary.timestamp_us[second_valid[0]])
    end = min(primary.timestamp_us[first_valid[-1]], secondary.timestamp_us[second_valid[-1]])
    mask = (secondary.timestamp_us >= start) & (secondary.timestamp_us <= end)
    if start > end or not np.any(mask & second_mask):
        return None, ComparisonResult.NO_OVERLAP
    return replace(secondary, timestamp_us=secondary.timestamp_us[mask],
                   values=secondary.values[mask], valid=second_mask[mask]), ComparisonResult.AVAILABLE
