"""Display-only GNSS evidence shared by the GUI and PNG export.

Recorded revision-3 rows are never replaced by a receiver-native recomputation.
This module filters unavailable/non-finite coordinates; it changes no admission,
weighting, estimator, or replay calculation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class HorizontalQualityTrace:
    timestamp_us: np.ndarray
    closure_norm_m: np.ndarray
    variance_scale: np.ndarray
    evidence_valid: np.ndarray
    source_kind: str


@dataclass(frozen=True, slots=True)
class ReceiverInformationTrace:
    timestamp_us: np.ndarray
    quality: np.ndarray


def ReceiverInformation_Build(dataset) -> ReceiverInformationTrace:
    records = dataset.Records_Get("GNSS_NATIVE")
    rows = sorted(
        (int(r.payload.get("receive_timestamp_us", r.timestamp_us)),
         tuple(float(r.payload.get(key, np.nan)) for key in (
             "horizontal_accuracy_m", "vertical_accuracy_m", "speed_accuracy_mps",
             "satellite_count")))
        for r in records
    )
    return ReceiverInformationTrace(
        np.asarray([r[0] for r in rows], dtype=np.int64),
        np.asarray([r[1] for r in rows], dtype=np.float64).reshape(-1, 4),
    )


def HorizontalQuality_Build(dataset, *, source_kind="recorded", window_evidence=None,
                            integrity_enabled=None):
    rows = []
    if source_kind == "recorded":
        for record in dataset.Records_Get("NAV_QUALITY"):
            p = record.payload
            if int(p["quality_revision"]) != 3:
                continue
            rows.append((int(p["evaluation_us"]), float(p["closure_norm_m"]),
                         float(p["variance_scale"]), bool(p["evidence_valid"]),
                         p["closure_en_m"]))
    elif source_kind == "recomputed":
        for p in window_evidence or ():
            # Native GNSS epochs are not MCU plot timestamps.
            timestamp = p.get("evaluation_us")
            if timestamp is None:
                continue
            en = np.asarray(p["closure_en"], dtype=np.float64)
            multiplier = (float(p["variance_scale"]) if integrity_enabled else 1.0
                          ) if integrity_enabled is not None else np.nan
            rows.append((int(timestamp), float(np.linalg.norm(en)),
                         multiplier, bool(p["valid"]), en))
    else:
        raise ValueError("gnss_quality_source_kind_invalid")
    rows.sort(key=lambda row: row[0])
    timestamps, closure, scale, valid = [], [], [], []
    for timestamp, norm, multiplier, usable, en in rows:
        coordinates = np.asarray(en, dtype=np.float64)
        usable = (usable and coordinates.shape == (2,) and np.isfinite(coordinates).all()
                  and np.isfinite(norm) and norm >= 0)
        timestamps.append(timestamp)
        closure.append(norm if usable else np.nan)
        scale.append(multiplier if np.isfinite(multiplier) and multiplier >= 1 else np.nan)
        valid.append(usable)
    return HorizontalQualityTrace(
        np.asarray(timestamps, dtype=np.int64), np.asarray(closure),
        np.asarray(scale), np.asarray(valid, dtype=bool), source_kind,
    )


def HorizontalQualitySummary_Get(trace, origin_us, start_s=0.0, end_s=float("inf")):
    """Summarize the selected interval separately from its last recorded row."""
    time = (trace.timestamp_us.astype(np.float64) - origin_us) * 1e-6
    selected = (time >= start_s) & (time <= end_s)
    indices = np.flatnonzero(selected)
    usable = selected & trace.evidence_valid
    scales = trace.variance_scale[selected]
    finite_scale = scales[np.isfinite(scales)]
    return {
        "source_kind": trace.source_kind, "samples": int(selected.sum()),
        "valid_samples": int(usable.sum()),
        "maximum_closure_m": float(np.max(trace.closure_norm_m[usable])) if usable.any() else None,
        "maximum_scale": float(np.max(finite_scale)) if finite_scale.size else None,
        "weighted_samples": int(np.count_nonzero(finite_scale > 1)),
        "end_scale": float(trace.variance_scale[indices[-1]]) if indices.size else None,
        "end_time_s": float(time[indices[-1]]) if indices.size else None,
        "end_evidence_valid": bool(trace.evidence_valid[indices[-1]]) if indices.size else False,
    }
