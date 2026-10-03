"""Horizontal display contract, mirrored in GSHC (no inter-app runtime dependency).

Input is real mission seconds and ENU metres. No resampling or boundary extrapolation.
Duplicate/reversed epochs, invalid samples, reanchors and gaps split geometry.
"""

from dataclasses import dataclass

import numpy as np

LABEL_IDS = (
    "title",
    "east",
    "north",
    "height",
    "start",
    "view_start",
    "end",
    "view_end",
    "deploy",
    "empty",
)


@dataclass(frozen=True, slots=True)
class HorizontalTrajectory:
    times_s: np.ndarray
    points_enu: np.ndarray
    edges_enu: np.ndarray
    edge_height_m: np.ndarray
    deploy_enu: np.ndarray | None
    start_clipped: bool
    end_clipped: bool
    gap_threshold_s: float


def HorizontalTrajectory_Build(
    times_s,
    points_enu,
    *,
    valid=None,
    origin_enu=(0, 0, 0),
    time_range=None,
    deploy_time_s=None,
    breaks_s=(),
    gap_threshold_s=None,
    mission_range=None,
):
    times = np.asarray(times_s, dtype=float)
    points = np.asarray(points_enu, dtype=float).reshape((-1, 3))
    if times.ndim != 1 or len(times) != len(points):
        raise ValueError("horizontal_trajectory_shape_invalid")
    origin = np.asarray(origin_enu, dtype=float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("horizontal_trajectory_origin_invalid")
    good = np.isfinite(times) & np.isfinite(points).all(axis=1)
    if valid is not None:
        flags = np.asarray(valid, dtype=bool)
        if flags.shape != times.shape:
            raise ValueError("horizontal_trajectory_validity_invalid")
        good &= flags
    cadence = np.diff(times)
    positive = cadence[np.isfinite(cadence) & (cadence > 0)]
    threshold = min(1.0, 2.5 * float(np.median(positive))) if positive.size else 0.0
    if gap_threshold_s is not None:
        threshold = float(gap_threshold_s)
        if not np.isfinite(threshold) or threshold < 0:
            raise ValueError("horizontal_trajectory_gap_invalid")
    if mission_range is not None:
        lower, upper = mission_range
        if not np.isfinite([lower, upper]).all() or lower > upper:
            raise ValueError("horizontal_trajectory_range_invalid")
        good &= (times >= lower) & (times <= upper)
    selected = good.copy()
    if time_range is not None:
        lower, upper = time_range
        if not np.isfinite([lower, upper]).all() or lower > upper:
            raise ValueError("horizontal_trajectory_range_invalid")
        selected &= (times >= lower) & (times <= upper)
    relative = points - origin
    joins = good[:-1] & good[1:] & (cadence > 0) & (cadence <= threshold)
    for stamp in breaks_s:
        joins &= ~((times[:-1] < stamp) & (stamp <= times[1:]))
    visible_joins = joins & selected[:-1] & selected[1:]
    edges = np.stack((relative[:-1][visible_joins], relative[1:][visible_joins]), axis=1)
    deploy = None
    if deploy_time_s is not None and np.isfinite(deploy_time_s):
        in_range = time_range is None or time_range[0] <= deploy_time_s <= time_range[1]
        exact = np.flatnonzero(selected & (times == deploy_time_s))
        if in_range and exact.size:
            deploy = relative[exact[-1]].copy()
        elif in_range:
            pair = np.flatnonzero(
                visible_joins & (times[:-1] < deploy_time_s) & (deploy_time_s < times[1:])
            )
            if pair.size == 1:
                i = pair[0]
                ratio = (deploy_time_s - times[i]) / cadence[i]
                deploy = relative[i] + ratio * (relative[i + 1] - relative[i])
    full_indices, view_indices = np.flatnonzero(good), np.flatnonzero(selected)
    clipped_start = bool(view_indices.size and view_indices[0] != full_indices[0])
    clipped_end = bool(view_indices.size and view_indices[-1] != full_indices[-1])
    arrays = (times[selected].copy(), relative[selected].copy(), edges, edges[:, :, 2].mean(axis=1))
    for array in arrays:
        array.setflags(write=False)
    return HorizontalTrajectory(*arrays, deploy, clipped_start, clipped_end, threshold)


def HorizontalTrajectory_Draw(figure, trajectory, labels, *, theme="light", title=""):
    """Identical GUI/export renderer: height colours, equal metric axes, external legend."""
    from matplotlib.cm import ScalarMappable
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize

    figure.clear()
    background, foreground = ("#20242b", "#e6e9ef") if theme == "dark" else ("#ffffff", "#1f2933")
    figure.set_facecolor(background)
    axis = figure.add_subplot(111)
    axis.set_facecolor(background)
    axis.set_xlabel(labels["east"], color=foreground)
    axis.set_ylabel(labels["north"], color=foreground)
    axis.set_title(title or labels["title"], color=foreground)
    axis.tick_params(colors=foreground)
    for spine in axis.spines.values():
        spine.set_color(foreground)
    axis.grid(alpha=0.25)
    axis.set_aspect("equal", adjustable="box")
    points = trajectory.points_enu
    if not len(points):
        axis.text(
            0.5,
            0.5,
            labels["empty"],
            ha="center",
            va="center",
            transform=axis.transAxes,
            color=foreground,
        )
        figure.subplots_adjust(left=0.13, right=0.9, bottom=0.18, top=0.90)
        _FigureFonts_Apply(figure, labels)
        return axis
    heights = points[:, 2]
    low, high = float(heights.min()), float(heights.max())
    constant = low == high
    norm = Normalize(low - 0.5 if constant else low, high + 0.5 if constant else high)
    collection = LineCollection(
        trajectory.edges_enu[:, :, :2], cmap="viridis", norm=norm, linewidths=2
    )
    collection.set_array(trajectory.edge_height_m)
    axis.add_collection(collection)
    # Isolated/short runs remain visible, without fabricating connecting lines.
    axis.scatter(points[:, 0], points[:, 1], c=heights, norm=norm, cmap="viridis", s=7)
    for point, marker, color, label in (
        (points[0], "o", "#16a34a", labels["view_start" if trajectory.start_clipped else "start"]),
        (trajectory.deploy_enu, "D", "#f59e0b", labels["deploy"]),
        (points[-1], "s", "#dc2626", labels["view_end" if trajectory.end_clipped else "end"]),
    ):
        if point is not None:
            axis.scatter(
                *point[:2],
                marker=marker,
                color=color,
                edgecolors=foreground,
                linewidths=0.6,
                s=45,
                label=label,
                zorder=5,
            )
    # Equal numeric spans keep even a straight northbound track in a usable
    # square plotting area; a narrow data bounding box must not collapse it.
    minimum, maximum = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
    centre = minimum + (maximum - minimum) / 2
    radius = max(float((maximum - minimum).max()) * 0.55, 1.0)
    axis.set_xlim(centre[0] - radius, centre[0] + radius)
    axis.set_ylim(centre[1] - radius, centre[1] + radius)
    bar = figure.colorbar(ScalarMappable(norm=norm, cmap="viridis"), ax=axis, pad=0.04)
    bar.set_label(labels["height"], color=foreground)
    bar.ax.tick_params(colors=foreground)
    if constant:
        bar.set_ticks([low])
    legend = axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=3,
        fontsize=9,
        facecolor=background,
        edgecolor=foreground,
    )
    for text in legend.get_texts():
        text.set_color(foreground)
    figure.subplots_adjust(left=0.13, right=0.90, bottom=0.23, top=0.90)
    _FigureFonts_Apply(figure, labels)
    return axis


def _FigureFonts_Apply(figure, labels):
    if any("\u4e00" <= character <= "\u9fff" for text in labels.values() for character in text):
        from matplotlib import font_manager
        from matplotlib.text import Text

        available = {font.name for font in font_manager.fontManager.ttflist}
        family = next(
            (
                name
                for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC")
                if name in available
            ),
            None,
        )
        if family:
            for text in figure.findobj(match=Text):
                text.set_fontfamily(family)
