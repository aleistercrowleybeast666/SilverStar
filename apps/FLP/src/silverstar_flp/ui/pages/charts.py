from __future__ import annotations

import colorsys

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QVector3D
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import (
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.math import Quaternion_RotateVector, Quaternion_ToEulerEnuDeg
from silverstar_flp.core.mission import (
    EstimatedLandingOnset_Get,
    FlightDisplayBounds_Get,
    MissionReplayBounds,
)
from silverstar_flp.core.time_range import DisplayIndices_Get
from silverstar_flp.core.trajectory import (
    TimeSeriesGapSummary_Get,
    TrajectoryBounds,
    TrajectoryBounds_Calculate,
    TrajectoryCameraDistance_Get,
    TrajectoryOrigin_Get,
    TrajectoryPhaseSegments_Build,
    TrajectoryPhaseValues_Get,
    TrajectoryPosition_At,
    TrajectoryPosition_NearEvent,
)
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_LANDING_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
    TrajectoryEventMesh_Get,
    TrajectoryMarkerWorldSizesFromExtent_Get,
    TrajectoryPhaseColor_Get,
)
from silverstar_flp.ui.plot_helpers import _Plot_Prepare, _Plot_Reset, _PlotViews_Reset
from silverstar_flp.ui.widgets import StandardComboBox

try:
    import pyqtgraph.opengl as gl
except Exception:  # OpenGL is optional; all 2D analysis remains available.
    gl = None


if gl is not None:

    class CameraLockGLViewWidget(gl.GLViewWidget):
        """3D view that can lock mouse rotation/panning while retaining wheel zoom."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._camera_locked = True

        def CameraLocked_Set(self, locked: bool) -> None:
            self._camera_locked = bool(locked)

        def mouseMoveEvent(self, event: object) -> None:
            if self._camera_locked:
                event.accept()
                return
            super().mouseMoveEvent(event)


_ROCKET_BASE_VERTICES = np.asarray(
    (
        (-0.35, -0.35, 0.0),
        (0.35, -0.35, 0.0),
        (0.35, 0.35, 0.0),
        (-0.35, 0.35, 0.0),
        (0.0, 0.0, 2.2),
    ),
    dtype=np.float32,
)
_ROCKET_FACES = np.asarray(
    (
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (3, 0, 4),
        (0, 1, 2),
        (0, 2, 3),
    ),
    dtype=np.uint32,
)


def _RocketVertices_Rotate(quaternion: np.ndarray) -> np.ndarray:
    return np.asarray(
        [Quaternion_RotateVector(quaternion, vertex) for vertex in _ROCKET_BASE_VERTICES],
        dtype=np.float32,
    )


def _RocketFaceColors_Get(theme: str) -> np.ndarray:
    return np.asarray(
        [QColor(color).getRgbF() for color in RocketFaceColors_Get(theme)],
        dtype=np.float32,
    )


def _RocketEdgeColor_Get(theme: str) -> tuple[float, float, float, float]:
    color = QColor("#E5E7EB" if theme == "dark" else "#334155")
    return color.getRgbF()


_TRACE_COLORS = (
    "#2563EB",
    "#16A34A",
    "#EA580C",
    "#9333EA",
    "#DB2777",
    "#0891B2",
    "#CA8A04",
    "#DC2626",
    "#4F46E5",
    "#059669",
    "#C2410C",
    "#7C3AED",
    "#BE185D",
    "#0E7490",
    "#A16207",
    "#B91C1C",
)


class TraceColorAllocator:
    """Allocate stable, non-repeating colors for one complete plot refresh."""

    def __init__(self) -> None:
        self._index = 0

    def Color_Next(self) -> str:
        index = self._index
        self._index += 1
        if index < len(_TRACE_COLORS):
            return _TRACE_COLORS[index]
        hue = (0.61803398875 * index + 0.13) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.88)
        return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def _Series_Plot(
    plot: pg.PlotWidget,
    series: TimeSeries | None,
    start_timestamp_us: int,
    *,
    end_timestamp_us: int | None = None,
    colors: TraceColorAllocator,
    prefix: str = "",
    width: float = 1.4,
    reference: bool = False,
) -> None:
    if series is None or series.count == 0:
        return
    selected_mask = series.timestamp_us >= np.uint64(max(start_timestamp_us, 0))
    if end_timestamp_us is not None:
        selected_mask &= series.timestamp_us <= np.uint64(max(end_timestamp_us, 0))
    selected = np.flatnonzero(selected_mask)
    if selected.size == 0:
        return
    full_t = series.timestamp_us[selected].astype(np.int64)
    full_v = series.valid[selected]
    cadence = np.diff(full_t)
    positive = cadence[cadence > 0]
    threshold = 3 * np.median(positive) if positive.size else np.inf
    broken = np.zeros(selected.size, dtype=bool)
    broken[:-1] = (~full_v[:-1]) | (~full_v[1:]) | (cadence > threshold)
    for stamp in series.metadata.get("discontinuity_timestamps_us", ()):
        index = int(np.searchsorted(full_t, stamp)) - 1
        if 0 <= index < broken.size:
            broken[index] = True
    envelope = DisplayIndices_Get(full_t, series.values[selected], full_v)
    counts = np.r_[0, np.cumsum(broken)]
    connections = np.zeros(envelope.size, dtype=bool)
    connections[:-1] = counts[envelope[1:]] == counts[envelope[:-1]]
    selected = selected[envelope]
    time = (
        series.timestamp_us[selected].astype(np.float64) - float(start_timestamp_us)
    ) * 1.0e-6
    values = np.asarray(series.values, dtype=np.float64)[selected].copy()
    valid = np.asarray(series.valid, dtype=np.bool_)[selected]
    style = Qt.PenStyle.DashLine if reference else Qt.PenStyle.SolidLine
    if values.ndim == 1:
        values[~valid] = np.nan
        plot.plot(
            time,
            values,
            connect=connections,
            pen=pg.mkPen(colors.Color_Next(), width=width, style=style),
            name=prefix or series.quantity,
        )
        return
    values[~valid, :] = np.nan
    for index in range(values.shape[1]):
        column = series.columns[index] if series.columns else str(index)
        plot.plot(
            time,
            values[:, index],
            connect=connections,
            pen=pg.mkPen(colors.Color_Next(), width=width, style=style),
            name=f"{prefix}{column}",
        )


def _EulerSeries_Create(series: TimeSeries) -> TimeSeries:
    values = np.asarray(series.values, dtype=np.float64)
    euler = np.full((series.count, 3), np.nan, dtype=np.float64)
    for index in np.flatnonzero(series.valid):
        try:
            euler[index] = Quaternion_ToEulerEnuDeg(values[index])
        except ValueError:
            continue
    return TimeSeries(
        timestamp_us=series.timestamp_us,
        values=euler,
        unit="deg",
        quantity="euler",
        source=series.source,
        valid=series.valid & np.all(np.isfinite(euler), axis=1),
        columns=("Roll", "Pitch", "Yaw"),
        metadata={"display_only": True, "quaternion_authoritative": True},
    )


def _Source_Label(
    translator: Translator,
    resolver: ChannelResolver,
    source_id: str,
) -> str:
    source = resolver.Source_Get(source_id)
    if source.kind == AnalysisSourceKind.RECORDED:
        return (
            translator.Text_Get("status.recorded") + " · " + resolver.RecordedNavigationSource_Get()
        )
    entry = resolver.store.SourceEntry_Get(source.source_id)
    if entry is None:
        return translator.Text_Get("status.recorded")
    mode_code = (
        "status.what_if"
        if entry.kind == AnalysisSourceKind.WHAT_IF
        else "status.recomputed"
    )
    if entry.analysis_only:
        mode_code = "diagnostic.analysis"
    return f"{entry.algorithm_name} · {translator.Text_Get(mode_code)} #{entry.run_index}"


def _RecordedSolution_Label(translator: Translator, solution_id: str) -> str:
    code = {
        "pure_ins": "solution.recorded_pure_ins",
        "kf6": "solution.recorded_kf6",
    }.get(solution_id, "status.recorded")
    return translator.Text_Get(code)


def _Event_Timestamp(dataset: FlightDataset, event_id: int) -> int | None:
    for record in sorted(dataset.Records_Get("EVENT"), key=lambda item: item.timestamp_us):
        if int(record.payload["event_id"]) == event_id:
            return record.timestamp_us
    return None


def _NearestIndex(timestamps: np.ndarray, timestamp_us: int) -> int:
    right = int(np.searchsorted(timestamps, timestamp_us, side="left"))
    if right <= 0:
        return 0
    if right >= timestamps.size:
        return timestamps.size - 1
    left = right - 1
    return (
        left
        if timestamp_us - int(timestamps[left]) <= int(timestamps[right]) - timestamp_us
        else right
    )


def _Position_At(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    position = TrajectoryPosition_At(series, timestamp_us)
    return None if position is None else np.asarray(position, dtype=np.float32)


def _Position_NearEvent(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    position = TrajectoryPosition_NearEvent(series, timestamp_us)
    return None if position is None else np.asarray(position, dtype=np.float32)


def _TrajectoryOrigin_Get(series: TimeSeries, start_timestamp_us: int) -> np.ndarray:
    return np.asarray(
        TrajectoryOrigin_Get(series, start_timestamp_us),
        dtype=np.float32,
    )


class FlightPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        self._resolver: ChannelResolver | None = None
        self._start_timestamp_us = 0
        self._end_timestamp_us = 0
        self._playback_time_us = 0
        self._position: TimeSeries | None = None
        self._reference_position: TimeSeries | None = None
        self._attitude: TimeSeries | None = None
        self._mission_bounds: MissionReplayBounds | None = None
        self._trajectory_bounds: TrajectoryBounds | None = None
        self._deploy_timestamp_us: int | None = None
        self._landing_timestamp_us: int | None = None
        self._trajectory_origin = np.zeros(3, dtype=np.float32)
        self._trajectory_camera_center = np.zeros(3, dtype=np.float32)
        self._trajectory_camera_distance = 40.0
        self._trajectory_marker_sizes = TrajectoryMarkerWorldSizesFromExtent_Get(1.0)
        self._deploy_marker_vertices = np.empty((0, 3), dtype=np.float32)
        self._landing_marker_vertices = np.empty((0, 3), dtype=np.float32)
        self._trajectory_camera_fit_count = 0

        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_value_label = QLabel("—")
        self.source_value_label.setObjectName("muted")
        self.source_detail_label = QLabel()
        self.source_detail_label.setObjectName("muted")
        self.source_detail_label.setWordWrap(True)
        source_row.addWidget(self.source_label)
        source_row.addWidget(self.source_value_label, 1)
        source_row.addWidget(self.source_detail_label, 2)
        self.reset_charts_button = QPushButton()
        self.reset_charts_button.clicked.connect(self._ChartViews_Reset)
        source_row.addWidget(self.reset_charts_button)
        layout.addLayout(source_row)

        self.tabs = QTabWidget()
        self.velocity_plot = self._Plot_Create()
        self.position_plot = self._Plot_Create()
        self.acceleration_plot = self._Plot_Create()
        self.angular_rate_plot = self._Plot_Create()
        self.attitude_widget = self._AttitudeWidget_Create()
        self.replay_3d_widget = self._Replay3d_Create()
        for widget in (
            self.velocity_plot,
            self.position_plot,
            self.acceleration_plot,
            self.angular_rate_plot,
            self.attitude_widget,
            self.replay_3d_widget,
        ):
            self.tabs.addTab(widget, "")
        layout.addWidget(self.tabs)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(40)
        self.playback_timer.timeout.connect(self._Playback_Tick)
        self.Language_Apply(translator)

    def _Plot_Create(self) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.addLegend()
        _Plot_Prepare(plot, self._theme)
        return plot

    def _ChartViews_Reset(self) -> None:
        _PlotViews_Reset(
            (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        )

    def _AttitudeWidget_Create(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.attitude_authority_label = QLabel()
        self.attitude_authority_label.setObjectName("muted")
        self.attitude_authority_label.setWordWrap(True)
        layout.addWidget(self.attitude_authority_label)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.quaternion_plot = self._Plot_Create()
        self.euler_plot = self._Plot_Create()
        splitter.addWidget(self.quaternion_plot)
        splitter.addWidget(self.euler_plot)
        splitter.setSizes((320, 320))
        layout.addWidget(splitter, 1)
        return widget

    def _Replay3d_Create(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.trajectory_quality_label = QLabel()
        self.trajectory_quality_label.setObjectName("muted")
        self.trajectory_quality_label.setWordWrap(True)
        layout.addWidget(self.trajectory_quality_label)
        self.trajectory_sources_label = QLabel()
        self.trajectory_sources_label.setObjectName("muted")
        self.trajectory_sources_label.setWordWrap(True)
        layout.addWidget(self.trajectory_sources_label)
        self.replay_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.replay_splitter.setChildrenCollapsible(False)
        self.attitude_3d_group = QGroupBox()
        attitude_layout = QVBoxLayout(self.attitude_3d_group)
        self.trajectory_3d_group = QGroupBox()
        trajectory_layout = QVBoxLayout(self.trajectory_3d_group)
        if gl is None:
            self.attitude_view = None
            self.trajectory_view = None
            self.rocket_mesh = None
            self.opengl_unavailable_label = QLabel()
            self.opengl_unavailable_label.setWordWrap(True)
            attitude_layout.addWidget(self.opengl_unavailable_label)
            trajectory_layout.addWidget(QLabel("—"))
            self._attitude_body_items = []
            self._world_items = []
            self._gl_text_items = []
        else:
            self.attitude_view = CameraLockGLViewWidget()
            self.attitude_view.setMinimumHeight(400)
            self.attitude_view.setCameraPosition(
                pos=QVector3D(0.0, 0.0, 0.7),
                distance=5.5,
                elevation=18.0,
                azimuth=-50.0,
            )
            self.attitude_grid = gl.GLGridItem()
            self.attitude_grid.setSize(4, 4)
            self.attitude_grid.setSpacing(0.5, 0.5)
            self.attitude_view.addItem(self.attitude_grid)
            self._attitude_world_items = [
                gl.GLLinePlotItem(width=2.0, antialias=True) for _ in range(3)
            ]
            self._attitude_body_items = [
                gl.GLLinePlotItem(width=3.0, antialias=True) for _ in range(3)
            ]
            for item in (*self._attitude_world_items, *self._attitude_body_items):
                self.attitude_view.addItem(item)
            rocket_data = gl.MeshData(
                vertexes=_ROCKET_BASE_VERTICES,
                faces=_ROCKET_FACES,
                faceColors=_RocketFaceColors_Get(self._theme),
            )
            self.rocket_mesh = gl.GLMeshItem(
                meshdata=rocket_data,
                smooth=False,
                computeNormals=False,
                drawEdges=True,
                edgeColor=_RocketEdgeColor_Get(self._theme),
                shader=None,
            )
            self.attitude_view.addItem(self.rocket_mesh)
            self._attitude_text_items = [
                gl.GLTextItem(pos=(0, 0, 0), text=text)
                for text in ("+E", "+N", "+U", "Xb", "Yb", "Zb")
            ]
            for item in self._attitude_text_items:
                self.attitude_view.addItem(item)
            attitude_layout.addWidget(self.attitude_view)

            self.trajectory_view = CameraLockGLViewWidget()
            self.trajectory_view.setMinimumHeight(400)
            self.trajectory_view.setCameraPosition(
                pos=QVector3D(0.0, 0.0, 0.0),
                distance=40.0,
                elevation=24.0,
                azimuth=-52.0,
            )
            self.trajectory_grid = gl.GLGridItem()
            self.trajectory_view.addItem(self.trajectory_grid)
            self._trajectory_world_items = [
                gl.GLLinePlotItem(width=2.0, antialias=True) for _ in range(3)
            ]
            self.recorded_path_line = gl.GLLinePlotItem(width=1.5, antialias=True)
            self.pre_deploy_line = gl.GLLinePlotItem(width=3.0, antialias=True)
            self.post_deploy_line = gl.GLLinePlotItem(width=3.0, antialias=True)
            deploy_vertices, deploy_faces = TrajectoryEventMesh_Get(
                np.zeros(3, dtype=np.float32),
                self._trajectory_marker_sizes[0],
            )
            deploy_colors = np.tile(
                np.asarray(QColor(TRAJECTORY_DEPLOY_COLOR).getRgbF(), dtype=np.float32),
                (deploy_faces.shape[0], 1),
            )
            self.deploy_marker = gl.GLMeshItem(
                meshdata=gl.MeshData(
                    vertexes=deploy_vertices.astype(np.float32),
                    faces=deploy_faces,
                    faceColors=deploy_colors,
                ),
                smooth=False,
                computeNormals=False,
                drawEdges=False,
                shader=None,
            )
            self.deploy_marker.setGLOptions("opaque")
            self.deploy_marker.setVisible(False)
            landing_vertices, landing_faces = TrajectoryEventMesh_Get(
                np.zeros(3, dtype=np.float32),
                self._trajectory_marker_sizes[2],
            )
            landing_colors = np.tile(
                np.asarray(QColor(TRAJECTORY_LANDING_COLOR).getRgbF(), dtype=np.float32),
                (landing_faces.shape[0], 1),
            )
            self.landing_marker = gl.GLMeshItem(
                meshdata=gl.MeshData(
                    vertexes=landing_vertices.astype(np.float32),
                    faces=landing_faces,
                    faceColors=landing_colors,
                ),
                smooth=False,
                computeNormals=False,
                drawEdges=False,
                shader=None,
            )
            self.landing_marker.setGLOptions("opaque")
            self.landing_marker.setVisible(False)
            self.current_marker = gl.GLScatterPlotItem(size=0.010, pxMode=False)
            self.current_marker.setDepthValue(28)
            self.landing_marker.setDepthValue(29)
            self.deploy_marker.setDepthValue(30)
            for item in (
                *self._trajectory_world_items,
                self.recorded_path_line,
                self.pre_deploy_line,
                self.post_deploy_line,
                self.deploy_marker,
                self.landing_marker,
                self.current_marker,
            ):
                self.trajectory_view.addItem(item)
            self._trajectory_text_items = [
                gl.GLTextItem(pos=(0, 0, 0), text=text)
                for text in ("E", "N", "U")
            ]
            for item in self._trajectory_text_items:
                self.trajectory_view.addItem(item)
            trajectory_layout.addWidget(self.trajectory_view)
            self._world_items = [
                *self._attitude_world_items,
                *self._trajectory_world_items,
            ]
            self._gl_text_items = [
                *self._attitude_text_items,
                *self._trajectory_text_items,
            ]
        self.attitude_axes_legend = QLabel()
        self.attitude_axes_legend.setObjectName("muted")
        self.attitude_axes_legend.setWordWrap(True)
        attitude_layout.addWidget(self.attitude_axes_legend)
        self.trajectory_axes_legend = QLabel()
        self.trajectory_axes_legend.setObjectName("muted")
        self.trajectory_axes_legend.setWordWrap(True)
        trajectory_layout.addWidget(self.trajectory_axes_legend)
        self.replay_splitter.addWidget(self.attitude_3d_group)
        self.replay_splitter.addWidget(self.trajectory_3d_group)
        self.replay_splitter.setStretchFactor(0, 1)
        self.replay_splitter.setStretchFactor(1, 1)
        self.replay_splitter.setSizes((650, 650))
        layout.addWidget(self.replay_splitter, 1)

        camera_controls = QHBoxLayout()
        self.camera_lock_button = QPushButton()
        self.camera_lock_button.setCheckable(True)
        self.camera_lock_button.toggled.connect(self._CameraLock_Toggled)
        self.reset_camera_button = QPushButton()
        self.reset_camera_button.clicked.connect(self._Cameras_Reset)
        self.camera_lock_button.setEnabled(gl is not None)
        self.reset_camera_button.setEnabled(gl is not None)
        camera_controls.addWidget(self.camera_lock_button)
        camera_controls.addWidget(self.reset_camera_button)
        camera_controls.addStretch(1)
        layout.addLayout(camera_controls)

        controls = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setObjectName("primaryButton")
        self.play_button.clicked.connect(self._Playback_Toggle)
        self.playback_slider = QSlider(Qt.Orientation.Horizontal)
        self.playback_slider.setRange(0, 10000)
        self.playback_slider.valueChanged.connect(self._ThreeD_Refresh)
        self.playback_speed_label = QLabel()
        self.playback_speed_combo = StandardComboBox()
        for value in (0.5, 1.0, 2.0, 4.0):
            self.playback_speed_combo.addItem(f"{value:g}×", value)
        self.playback_speed_combo.setCurrentIndex(1)
        self.playback_time_label = QLabel("—")
        self.playback_time_label.setMinimumWidth(190)
        controls.addWidget(self.play_button)
        controls.addWidget(self.playback_slider, 1)
        controls.addWidget(self.playback_speed_label)
        controls.addWidget(self.playback_speed_combo)
        controls.addWidget(self.playback_time_label)
        layout.addLayout(controls)
        return widget

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver | None = None,
    ) -> None:
        self._dataset = dataset
        self._resolver = resolver or ChannelResolver(dataset, ReplayResultStore())
        self._Plots_Refresh()

    def _Plots_Refresh(self, *, reset_camera: bool = True) -> None:
        if self._dataset is None or self._resolver is None:
            return
        source_id = self._resolver.store.ActiveSource_Get().source_id
        source = self._resolver.Source_Get(source_id)
        self.source_value_label.setText(
            _Source_Label(self._translator, self._resolver, source_id)
        )
        start = self._dataset.start_timestamp_us
        if start is None:
            start = self._dataset.diagnostics.first_timestamp_us or 0
            self.source_detail_label.setText(
                self._translator.Text_Get("flight.start_fallback")
            )
        else:
            self.source_detail_label.setText(
                self._translator.Text_Get("flight.start_crop", timestamp=start)
            )
        self.source_detail_label.setToolTip("")
        self._start_timestamp_us = start
        _Plot_Reset(
            (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        )
        color_allocators = {
            plot: TraceColorAllocator()
            for plot in (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        }
        velocity = self._resolver.Series_Get("navigation.velocity_enu", source_id)
        position = self._resolver.Series_Get("navigation.position_enu", source_id)
        attitude = self._resolver.Series_Get("attitude.q_nb", source_id)
        self._mission_bounds = FlightDisplayBounds_Get(
            self._dataset, self._resolver.MissionReplayBounds_Get(source_id)
        )
        end = self._mission_bounds.end_timestamp_us
        onset = EstimatedLandingOnset_Get(self._dataset)
        confirmed_end = self._resolver.MissionReplayBounds_Get(source_id).end_timestamp_us
        if onset is not None and onset < confirmed_end:
            self.source_detail_label.setText(
                self.source_detail_label.text() + " · " +
                self._translator.Text_Get(
                    "flight.estimated_landing_onset",
                    seconds=(onset - start) * 1e-6,
                )
            )
        selected_label = _Source_Label(self._translator, self._resolver, source_id)
        reference_position = None
        if source.kind != AnalysisSourceKind.RECORDED:
            reference_position = self._resolver.RecordedSeries_Get("navigation.position_enu")
        self._reference_position = reference_position
        self.trajectory_sources_label.setText(
            self._translator.Text_Get(
                "flight.trajectory_two_sources",
                recorded=_Source_Label(
                    self._translator, self._resolver,
                    ReplayResultStore.RECORDED_SOURCE_ID,
                ),
                selected=selected_label,
            ) if reference_position is not None else ""
        )
        reference_label = _Source_Label(
            self._translator, self._resolver, ReplayResultStore.RECORDED_SOURCE_ID
        )
        for channel, selected_series, plot in (
            ("navigation.velocity_enu", velocity, self.velocity_plot),
            ("navigation.position_enu", position, self.position_plot),
            ("attitude.q_nb", attitude, self.quaternion_plot),
        ):
            if source.kind != AnalysisSourceKind.RECORDED:
                recorded = self._resolver.RecordedSeries_Get(channel)
                _Series_Plot(
                    plot, recorded, start, end_timestamp_us=end,
                    colors=color_allocators[plot],
                    prefix=f"{reference_label} · ",
                    width=1.4, reference=True,
                )
                if channel == "attitude.q_nb" and recorded is not None:
                    _Series_Plot(
                        self.euler_plot, _EulerSeries_Create(recorded), start,
                        end_timestamp_us=end, colors=color_allocators[self.euler_plot],
                        prefix=f"{reference_label} · ",
                        width=1.4, reference=True,
                    )
            _Series_Plot(
                plot, selected_series, start, end_timestamp_us=end,
                colors=color_allocators[plot], prefix=f"{selected_label} · ", width=1.7,
            )
        if attitude is not None:
            _Series_Plot(
                self.euler_plot, _EulerSeries_Create(attitude), start,
                end_timestamp_us=end, colors=color_allocators[self.euler_plot],
                prefix=f"{selected_label} · ", width=1.7,
            )
        _Series_Plot(
            self.acceleration_plot,
            self._resolver.RecordedSeries_Get("imu.corrected.accel_b"),
            start,
            end_timestamp_us=end,
            colors=color_allocators[self.acceleration_plot],
            prefix=f"{self._translator.Text_Get('status.recorded')} · ",
        )
        _Series_Plot(
            self.angular_rate_plot,
            self._resolver.RecordedSeries_Get("imu.corrected.gyro_b"),
            start,
            end_timestamp_us=end,
            colors=color_allocators[self.angular_rate_plot],
            prefix=f"{self._translator.Text_Get('status.recorded')} · ",
        )
        self._position = position
        self._attitude = attitude
        self._deploy_timestamp_us = _Event_Timestamp(self._dataset, 0x29)
        self._landing_timestamp_us = _Event_Timestamp(self._dataset, 0x2A)
        self._trajectory_bounds = (
            TrajectoryBounds_Calculate(position, self._mission_bounds)
            if position is not None else None
        )
        self._trajectory_origin = (
            np.asarray(self._trajectory_bounds.origin_enu, dtype=np.float32)
            if self._trajectory_bounds is not None
            else np.zeros(3, dtype=np.float32)
        )
        self._end_timestamp_us = end
        self._playback_time_us = start
        self.playback_slider.blockSignals(True)
        self.playback_slider.setValue(0)
        self.playback_slider.blockSignals(False)
        self._Trajectory3d_Prepare(reset_camera=reset_camera)
        self._ThreeD_Refresh(0)

    def TimeRange_Set(self, start_us: int, end_us: int) -> None:
        visual_end = self._mission_bounds.end_timestamp_us if self._mission_bounds else end_us
        self._start_timestamp_us = min(start_us, visual_end)
        self._end_timestamp_us = min(max(end_us, self._start_timestamp_us), visual_end)
        self._playback_time_us = start_us
        self.playback_slider.setValue(0)
        self._Trajectory3d_Prepare(reset_camera=False)
        self._ThreeD_Refresh(0)

    def _CameraLock_Toggled(self, unlocked: bool) -> None:
        if gl is not None:
            self.attitude_view.CameraLocked_Set(not unlocked)
            self.trajectory_view.CameraLocked_Set(not unlocked)
        self.camera_lock_button.setText(
            self._translator.Text_Get(
                "action.lock_camera" if unlocked else "action.unlock_camera"
            )
        )

    def _Cameras_Reset(self) -> None:
        if gl is None:
            return
        self.attitude_view.setCameraPosition(
            pos=QVector3D(0.0, 0.0, 0.7),
            distance=5.5,
            elevation=18.0,
            azimuth=-50.0,
        )
        if self._trajectory_bounds is not None:
            self._trajectory_camera_center = np.asarray(
                self._trajectory_bounds.center_enu,
                dtype=np.float32,
            )
            aspect_ratio = max(float(self.trajectory_view.width()), 1.0) / max(
                float(self.trajectory_view.height()),
                1.0,
            )
            self._trajectory_camera_distance = TrajectoryCameraDistance_Get(
                self._trajectory_bounds,
                horizontal_fov_deg=float(self.trajectory_view.opts.get("fov", 60.0)),
                aspect_ratio=aspect_ratio,
            )
            self._trajectory_camera_fit_count += 1
        center = self._trajectory_camera_center
        self.trajectory_view.setCameraPosition(
            pos=QVector3D(float(center[0]), float(center[1]), float(center[2])),
            distance=self._trajectory_camera_distance,
            elevation=24.0,
            azimuth=-52.0,
        )

    def _Trajectory3d_Prepare(self, *, reset_camera: bool) -> None:
        if self._position is not None:
            quality = TimeSeriesGapSummary_Get(
                self._position, self._start_timestamp_us, self._end_timestamp_us)
            self.trajectory_quality_label.setText(self._translator.Text_Get(
                "flight.trajectory_quality", gaps=quality["timestamp_gap_segments"],
                invalid=quality["invalid_samples"], threshold=quality["gap_threshold_us"] / 1000))
        else:
            self.trajectory_quality_label.clear()
        self._trajectory_phase_segments = (
            TrajectoryPhaseSegments_Build(
                self._position,
                (() if self._deploy_timestamp_us is None else (self._deploy_timestamp_us,)),
                start_timestamp_us=self._start_timestamp_us,
                end_timestamp_us=self._end_timestamp_us,
            ) if self._position is not None else ()
        )
        if gl is None:
            return
        axis_colors = (
            (0.95, 0.2, 0.2, 1.0),
            (0.2, 0.9, 0.35, 1.0),
            (0.2, 0.5, 1.0, 1.0),
        )
        if self._trajectory_bounds is not None:
            spans = np.asarray(self._trajectory_bounds.span_enu, dtype=np.float32)
            extent = max(float(self._trajectory_bounds.max_span), 1.0)
            self._trajectory_camera_center = np.asarray(
                self._trajectory_bounds.center_enu,
                dtype=np.float32,
            )
            self._trajectory_marker_sizes = TrajectoryMarkerWorldSizesFromExtent_Get(
                self._trajectory_bounds.max_span
            )
        else:
            spans = np.ones(3, dtype=np.float32)
            extent = 4.0
            self._trajectory_camera_center = np.zeros(3, dtype=np.float32)
            self._trajectory_camera_distance = 8.0
            self._trajectory_marker_sizes = TrajectoryMarkerWorldSizesFromExtent_Get(1.0)
        axis_length = max(float(np.max(spans)) * 0.2, 1.0)
        for axis, item in enumerate(self._trajectory_world_items):
            endpoint = np.zeros(3, dtype=np.float32)
            endpoint[axis] = axis_length
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=axis_colors[axis],
                width=2.0,
            )
            self._trajectory_text_items[axis].setData(pos=tuple(endpoint))
        self.trajectory_grid.setSize(extent * 1.3, extent * 1.3)
        spacing = max(extent / 10.0, 0.5)
        self.trajectory_grid.setSpacing(spacing, spacing)
        if reset_camera:
            self._Cameras_Reset()

    def _Playback_Toggle(self) -> None:
        if self.playback_timer.isActive():
            self.playback_timer.stop()
        else:
            if self.playback_slider.value() >= 10000:
                self.playback_slider.setValue(0)
            self.playback_timer.start()
        self._PlaybackButton_Refresh()

    def _PlaybackButton_Refresh(self) -> None:
        self.play_button.setText(
            self._translator.Text_Get(
                "action.pause" if self.playback_timer.isActive() else "action.play"
            )
        )

    def _Playback_Tick(self) -> None:
        if self._end_timestamp_us <= self._start_timestamp_us:
            self.playback_timer.stop()
            self._PlaybackButton_Refresh()
            return
        speed = float(self.playback_speed_combo.currentData() or 1.0)
        self._playback_time_us += int(
            self.playback_timer.interval() * 1000 * speed
        )
        if self._playback_time_us >= self._end_timestamp_us:
            self._playback_time_us = self._end_timestamp_us
            self.playback_timer.stop()
            self._PlaybackButton_Refresh()
        value = int(
            (self._playback_time_us - self._start_timestamp_us)
            * 10000
            / (self._end_timestamp_us - self._start_timestamp_us)
        )
        self.playback_slider.setValue(max(0, min(10000, value)))

    def _ThreeD_Refresh(self, value: int) -> None:
        if self._end_timestamp_us <= self._start_timestamp_us:
            timestamp_us = self._start_timestamp_us
        else:
            timestamp_us = int(
                self._start_timestamp_us
                + (self._end_timestamp_us - self._start_timestamp_us)
                * value
                / 10000
            )
        self._playback_time_us = timestamp_us
        mission_time = (
            timestamp_us
            - (
                self._mission_bounds.start_timestamp_us
                if self._mission_bounds
                else self._start_timestamp_us
            )
        ) * 1.0e-6
        self.playback_time_label.setText(
            self._translator.Text_Get("flight.mission_time", value=mission_time)
        )
        if gl is None:
            return
        self._Attitude3d_Refresh(timestamp_us)
        self._Trajectory3d_Refresh(timestamp_us)

    def _Attitude3d_Refresh(self, timestamp_us: int) -> None:
        if self._attitude is None or self._attitude.count == 0:
            return
        index = _NearestIndex(self._attitude.timestamp_us, timestamp_us)
        quaternion = np.asarray(self._attitude.values[index], dtype=np.float32)
        try:
            rotated_vertices = _RocketVertices_Rotate(quaternion)
        except ValueError:
            return
        mesh_data = gl.MeshData(
            vertexes=rotated_vertices,
            faces=_ROCKET_FACES,
            faceColors=_RocketFaceColors_Get(self._theme),
        )
        self.rocket_mesh.setMeshData(
            meshdata=mesh_data,
            edgeColor=_RocketEdgeColor_Get(self._theme),
        )
        colors = (
            (0.95, 0.2, 0.2, 1.0),
            (0.2, 0.9, 0.35, 1.0),
            (0.2, 0.5, 1.0, 1.0),
        )
        identity = np.eye(3, dtype=np.float32)
        body_lengths = np.asarray((1.1, 1.1, 1.6), dtype=np.float32)
        for axis, item in enumerate(self._attitude_world_items):
            endpoint = identity[axis] * 1.25
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=colors[axis],
                width=2.0,
            )
            self._attitude_text_items[axis].setData(pos=tuple(endpoint))
        for axis, item in enumerate(self._attitude_body_items):
            endpoint = Quaternion_RotateVector(
                quaternion,
                identity[axis] * body_lengths[axis],
            )
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=colors[axis],
                width=3.0,
            )
            self._attitude_text_items[axis + 3].setData(pos=tuple(endpoint))

    def _Trajectory3d_Refresh(self, timestamp_us: int) -> None:
        empty = np.empty((0, 3), dtype=np.float32)
        reference = self._reference_position
        if reference is not None:
            values = np.asarray(reference.values, dtype=np.float32)
            valid = (
                reference.valid & np.all(np.isfinite(values), axis=1)
                & (reference.timestamp_us >= np.uint64(self._start_timestamp_us))
                & (reference.timestamp_us <= np.uint64(timestamp_us))
            )
            recorded_points = values[valid] - self._trajectory_origin
            self.recorded_path_line.setData(
                pos=recorded_points if len(recorded_points) > 1 else empty,
                color=(0.55, 0.57, 0.62, 0.65), width=1.5,
            )
        else:
            self.recorded_path_line.setData(pos=empty)
        if self._position is None or self._position.count == 0:
            self.pre_deploy_line.setData(pos=empty)
            self.post_deploy_line.setData(pos=empty)
            self.deploy_marker.setVisible(False)
            self._deploy_marker_vertices = empty
            self.landing_marker.setVisible(False)
            self._landing_marker_vertices = empty
            self.current_marker.setData(pos=empty)
            return
        raw_values = np.asarray(self._position.values, dtype=np.float32)
        finite = np.all(np.isfinite(raw_values), axis=1)
        valid = (
            self._position.valid
            & finite
            & (self._position.timestamp_us >= np.uint64(self._start_timestamp_us))
            & (self._position.timestamp_us <= np.uint64(timestamp_us))
        )
        points = raw_values[valid] - self._trajectory_origin
        if points.size == 0:
            self.pre_deploy_line.setData(pos=empty)
            self.post_deploy_line.setData(pos=empty)
            self.deploy_marker.setVisible(False)
            self._deploy_marker_vertices = empty
            self.landing_marker.setVisible(False)
            self._landing_marker_vertices = empty
            self.current_marker.setData(pos=empty)
            return
        deploy = self._deploy_timestamp_us
        pre, post = (
            TrajectoryPhaseValues_Get(
                self._trajectory_phase_segments, phase,
                timestamp_us=timestamp_us, origin=self._trajectory_origin,
                max_points_per_segment=10000,
            ).astype(np.float32)
            for phase in (0, 1)
        )
        self.pre_deploy_line.setData(
            pos=pre,
            color=QColor(TRAJECTORY_PRE_DEPLOY_COLOR).getRgbF(),
            width=3.0,
        )
        self.post_deploy_line.setData(
            pos=post,
            color=QColor(TRAJECTORY_POST_DEPLOY_COLOR).getRgbF(),
            width=3.0,
        )
        current = points[-1]
        current_color = TrajectoryPhaseColor_Get(timestamp_us, deploy)
        deploy_size, current_size, landing_size = self._trajectory_marker_sizes
        landing_reached = (
            self._landing_timestamp_us is not None
            and timestamp_us >= self._landing_timestamp_us
        )
        if landing_reached:
            self.current_marker.setData(pos=empty)
        else:
            self.current_marker.setData(
                pos=np.asarray([current], dtype=np.float32),
                color=QColor(current_color).getRgbF(),
                size=current_size,
            )
        deploy_point = (
            _Position_At(self._position, deploy)
            if deploy is not None and timestamp_us >= deploy
            else None
        )
        if deploy_point is not None:
            deploy_point = deploy_point - self._trajectory_origin
        if deploy_point is None:
            self.deploy_marker.setVisible(False)
            self._deploy_marker_vertices = empty
        else:
            deploy_vertices, deploy_faces = TrajectoryEventMesh_Get(
                deploy_point,
                deploy_size,
            )
            deploy_colors = np.tile(
                np.asarray(QColor(TRAJECTORY_DEPLOY_COLOR).getRgbF(), dtype=np.float32),
                (deploy_faces.shape[0], 1),
            )
            self._deploy_marker_vertices = deploy_vertices.astype(np.float32)
            self.deploy_marker.setMeshData(
                meshdata=gl.MeshData(
                    vertexes=self._deploy_marker_vertices,
                    faces=deploy_faces,
                    faceColors=deploy_colors,
                )
            )
            self.deploy_marker.setVisible(True)
        landing_point = (
            _Position_NearEvent(self._position, self._landing_timestamp_us)
            if self._landing_timestamp_us is not None
            and timestamp_us >= self._landing_timestamp_us
            else None
        )
        if landing_point is not None:
            landing_point = landing_point - self._trajectory_origin
        if landing_point is None:
            self.landing_marker.setVisible(False)
            self._landing_marker_vertices = empty
        else:
            landing_vertices, landing_faces = TrajectoryEventMesh_Get(
                landing_point,
                landing_size,
            )
            landing_colors = np.tile(
                np.asarray(QColor(TRAJECTORY_LANDING_COLOR).getRgbF(), dtype=np.float32),
                (landing_faces.shape[0], 1),
            )
            self._landing_marker_vertices = landing_vertices.astype(np.float32)
            self.landing_marker.setMeshData(
                meshdata=gl.MeshData(
                    vertexes=self._landing_marker_vertices,
                    faces=landing_faces,
                    faceColors=landing_colors,
                )
            )
            self.landing_marker.setVisible(True)

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in (
            self.velocity_plot,
            self.position_plot,
            self.acceleration_plot,
            self.angular_rate_plot,
            self.quaternion_plot,
            self.euler_plot,
        ):
            _Plot_Prepare(plot, theme)
        if gl is not None:
            background = QColor("#111827" if theme == "dark" else "#FFFFFF")
            grid = QColor("#64748B" if theme == "dark" else "#94A3B8")
            foreground = QColor("#E5E7EB" if theme == "dark" else "#172033")
            self.attitude_view.setBackgroundColor(background)
            self.trajectory_view.setBackgroundColor(background)
            self.attitude_grid.setColor(grid)
            self.trajectory_grid.setColor(grid)
            for item in self._gl_text_items:
                item.setData(color=foreground)
            if self._attitude is not None and self._attitude.count:
                self._Attitude3d_Refresh(self._playback_time_us)
            else:
                mesh_data = gl.MeshData(
                    vertexes=_ROCKET_BASE_VERTICES,
                    faces=_ROCKET_FACES,
                    faceColors=_RocketFaceColors_Get(theme),
                )
                self.rocket_mesh.setMeshData(
                    meshdata=mesh_data,
                    edgeColor=_RocketEdgeColor_Get(theme),
                )
            self._Trajectory3d_Refresh(self._playback_time_us)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.source_label.setText(translator.Text_Get("label.analysis_source"))
        self.velocity_plot.setTitle(translator.Text_Get("chart.velocity_enu"))
        self.position_plot.setTitle(translator.Text_Get("chart.position_enu"))
        self.acceleration_plot.setTitle(
            translator.Text_Get("chart.corrected_acceleration")
        )
        self.angular_rate_plot.setTitle(
            translator.Text_Get("chart.corrected_angular_rate")
        )
        self.quaternion_plot.setTitle(translator.Text_Get("chart.quaternion_wxyz"))
        self.euler_plot.setTitle(translator.Text_Get("chart.euler_display"))
        self.attitude_authority_label.setText(
            translator.Text_Get("flight.attitude_authority")
        )
        tab_codes = (
            "tab.velocity",
            "tab.position",
            "tab.acceleration",
            "tab.angular_rate",
            "tab.attitude",
            "tab.replay_3d",
        )
        for index, code in enumerate(tab_codes):
            self.tabs.setTabText(index, translator.Text_Get(code))
        self.attitude_3d_group.setTitle(translator.Text_Get("flight.attitude_3d"))
        self.trajectory_3d_group.setTitle(
            translator.Text_Get("flight.trajectory_3d")
        )
        self.attitude_axes_legend.setText(
            translator.Text_Get("flight.attitude_axes_legend")
        )
        self.trajectory_axes_legend.setText(
            translator.Text_Get("flight.trajectory_axes_legend")
        )
        self.playback_speed_label.setText(
            translator.Text_Get("flight.playback_speed")
        )
        self.reset_camera_button.setText(translator.Text_Get("action.reset_view"))
        self.reset_charts_button.setText(translator.Text_Get("action.reset_charts"))
        self.reset_charts_button.setToolTip(
            translator.Text_Get("action.reset_charts_tooltip")
        )
        self._CameraLock_Toggled(self.camera_lock_button.isChecked())
        self._PlaybackButton_Refresh()
        if gl is None:
            self.opengl_unavailable_label.setText(
                translator.Text_Get("status.opengl_unavailable")
            )
        if self._dataset is not None and self._resolver is not None:
            self._Plots_Refresh(reset_camera=False)
