from __future__ import annotations

import numpy as np

ROCKET_FACE_COLORS_LIGHT = (
    "#FF5A5F",
    "#22C55E",
    "#3B82F6",
    "#F5B942",
    "#A8B3C2",
    "#7F8B9D",
)

ROCKET_FACE_COLORS_DARK = (
    "#FF7B86",
    "#4ADE80",
    "#60A5FA",
    "#FACC15",
    "#CBD5E1",
    "#94A3B8",
)

TRAJECTORY_PRE_DEPLOY_COLOR = "#EF4444"
TRAJECTORY_POST_DEPLOY_COLOR = "#3B82F6"
TRAJECTORY_DEPLOY_COLOR = "#F97316"
TRAJECTORY_LANDING_COLOR = "#8B5CF6"

_TRAJECTORY_DEPLOY_MARKER_RATIO = 0.035
_TRAJECTORY_CURRENT_MARKER_RATIO = 0.010
_TRAJECTORY_LANDING_MARKER_RATIO = 0.030
_EVENT_MARKER_UNIT_VERTICES = np.asarray(
    (
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ),
    dtype=np.float64,
)
_EVENT_MARKER_FACES = np.asarray(
    (
        (0, 2, 4),
        (2, 1, 4),
        (1, 3, 4),
        (3, 0, 4),
        (2, 0, 5),
        (1, 2, 5),
        (3, 1, 5),
        (0, 3, 5),
    ),
    dtype=np.uint32,
)


def RocketFaceColors_Get(theme: str) -> tuple[str, ...]:
    return ROCKET_FACE_COLORS_DARK if theme == "dark" else ROCKET_FACE_COLORS_LIGHT


def TrajectoryPhaseColor_Get(
    timestamp_us: int,
    deploy_timestamp_us: int | None,
) -> str:
    if deploy_timestamp_us is not None and timestamp_us >= deploy_timestamp_us:
        return TRAJECTORY_POST_DEPLOY_COLOR
    return TRAJECTORY_PRE_DEPLOY_COLOR


def TrajectoryCharacteristicExtent_Get(
    values: np.ndarray,
    *,
    minimum_extent: float = 1.0,
) -> float:
    points = np.asarray(values, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or points.size == 0:
        return float(minimum_extent)
    finite = points[np.all(np.isfinite(points), axis=1)]
    if finite.size == 0:
        return float(minimum_extent)
    spans = np.max(finite, axis=0) - np.min(finite, axis=0)
    return max(float(np.max(spans)), float(minimum_extent))


def TrajectoryMarkerWorldSizes_Get(values: np.ndarray) -> tuple[float, float, float]:
    """Return Deploy, Current, and Landing marker diameters in trajectory units."""

    return TrajectoryMarkerWorldSizesFromExtent_Get(
        TrajectoryCharacteristicExtent_Get(values)
    )


def TrajectoryMarkerWorldSizesFromExtent_Get(
    maximum_span: float,
) -> tuple[float, float, float]:
    """Return marker diameters from a cached trajectory span."""

    extent = max(float(maximum_span), 1.0)
    if not np.isfinite(extent):
        extent = 1.0
    return (
        extent * _TRAJECTORY_DEPLOY_MARKER_RATIO,
        extent * _TRAJECTORY_CURRENT_MARKER_RATIO,
        extent * _TRAJECTORY_LANDING_MARKER_RATIO,
    )


def TrajectoryEventMesh_Get(
    center: np.ndarray,
    diameter: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return an opaque octahedron marker centered in trajectory world coordinates."""

    position = np.asarray(center, dtype=np.float64)
    size = float(diameter)
    if position.shape != (3,) or not np.all(np.isfinite(position)):
        raise ValueError("trajectory_event_marker_center_invalid")
    if not np.isfinite(size) or size <= 0.0:
        raise ValueError("trajectory_event_marker_size_invalid")
    vertices = position + _EVENT_MARKER_UNIT_VERTICES * (size * 0.5)
    return vertices, _EVENT_MARKER_FACES.copy()
