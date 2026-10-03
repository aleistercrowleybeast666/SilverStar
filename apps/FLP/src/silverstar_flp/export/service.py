from __future__ import annotations

import colorsys
import csv
import hashlib
import json
import logging
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build
from silverstar_flp.analysis.gnss_vertical_consistency import GnssVerticalConsistency_Build
from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.analysis_source import (
    AnalysisSource,
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.context import TaskCancelledError, TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.horizontal_trajectory import (
    LABEL_IDS,
    HorizontalTrajectory_Build,
    HorizontalTrajectory_Draw,
)
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.math import Quaternion_RotateVector
from silverstar_flp.core.mission import (
    FlightDisplayBounds_Get,
    MissionReplayBounds,
    MissionReplayBounds_Get,
    MissionReplayEndReason,
)
from silverstar_flp.core.time_range import PlotArrays_Get
from silverstar_flp.core.trajectory import (
    TimeSeriesGapSummary_Get,
    TrajectoryBounds,
    TrajectoryBounds_Calculate,
    TrajectoryOrigin_Get,
    TrajectoryPhaseSegment,
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
from silverstar_flp.export.plot_metadata import (
    ChannelDisplayMetadata_Get,
    ComponentLabel_Get,
)
from silverstar_flp.export.ranges import ExportPages_Get, GifMetadata_Get, PlotDirectory
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmMetadata,
    AlgorithmResult,
    EstimatorVisualizationSpec,
    FullCovarianceSpec,
    MeasurementGroupSpec,
    StateGroupSpec,
)
from silverstar_flp.plugins.registry import PluginRegistry, builtin_registry


class ExportLanguage(StrEnum):
    FOLLOW_UI = "follow_ui"
    ZH = "zh_CN"
    EN = "en_US"


class ExportTheme(StrEnum):
    FOLLOW_UI = "follow_ui"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class ExportOptions:
    language: ExportLanguage = ExportLanguage.FOLLOW_UI
    ui_language: str = "zh_CN"
    theme: ExportTheme = ExportTheme.FOLLOW_UI
    ui_theme: str = "light"
    include_overview: bool = True
    include_diagnostics: bool = True
    include_events: bool = True
    include_csv: bool = True
    include_full_covariance_keyframes: bool = True
    include_plots: bool = True
    include_trajectory_3d: bool = True
    include_attitude_gif: bool = True
    selected_channels: tuple[str, ...] = ()
    page_mode: str = "30"
    page_duration: float = 30.0
    gif_range_mode: str = "Current View"
    current_range: tuple[float, float] | None = None
    source_mode: str = "follow_ui"
    source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", ExportLanguage(self.language))
        object.__setattr__(self, "theme", ExportTheme(self.theme))
        object.__setattr__(self, "ui_language", str(self.ui_language))
        if self.source_mode not in ("follow_ui", "explicit"):
            raise ValueError("export_source_mode_invalid")
        if self.source_mode == "explicit" and not self.source_id:
            raise ValueError("export_source_id_required")
        if self.source_id is not None and not isinstance(self.source_id, str):
            raise ValueError("export_source_id_invalid")
        if self.ui_theme not in ("light", "dark"):
            raise ValueError("export_ui_theme_invalid")
        if self.page_mode not in ('5', '10', '30', '60', '120', 'Custom', 'Current View', 'Full'):
            raise ValueError('export_page_mode_invalid')
        if not np.isfinite(self.page_duration) or self.page_duration <= 0:
            raise ValueError('export_page_duration_invalid')
        if self.gif_range_mode not in ('Current View', 'Full'):
            raise ValueError('export_gif_range_invalid')
        if self.current_range is not None:
            start, end = self.current_range
            if not np.isfinite([start, end]).all() or start < 0 or end < start:
                raise ValueError('export_current_range_invalid')

        object.__setattr__(
            self,
            "selected_channels",
            tuple(str(channel_id) for channel_id in self.selected_channels),
        )


@dataclass(frozen=True, slots=True)
class ExportGenerated:
    item_id: str
    localized_name: str
    path: Path


@dataclass(frozen=True, slots=True)
class ExportSkipped:
    item_id: str
    localized_name: str
    skipped_reason: str


@dataclass(frozen=True, slots=True)
class ExportFailure:
    item_id: str
    localized_name: str
    exception_type: str
    exception_message: str

    @property
    def item(self) -> str:
        return self.item_id

    @property
    def error(self) -> str:
        return f"{self.exception_type}: {self.exception_message}"


@dataclass(frozen=True, slots=True)
class ExportManifest:
    output_directory: Path
    files: tuple[Path, ...]
    language: ExportLanguage
    theme: ExportTheme
    failures: tuple[ExportFailure, ...] = ()
    generated: tuple[ExportGenerated, ...] = ()
    skipped: tuple[ExportSkipped, ...] = ()

    def ManifestPath_Get(self) -> Path | None:
        suffix = "_ZH" if self.language == ExportLanguage.ZH else "_EN"
        candidate = self.output_directory / f"Export_Manifest{suffix}.json"
        return candidate if candidate in self.files else None

    def FailureReportPath_Get(self) -> Path | None:
        suffix = "_ZH" if self.language == ExportLanguage.ZH else "_EN"
        candidate = self.output_directory / f"Export_Failures{suffix}.txt"
        return candidate if candidate in self.files else None


_LABELS = {
    ExportLanguage.ZH: {
        "time": "任务时间",
        "value": "数值",
        "valid": "有效",
        "trajectory": "三维飞行轨迹（任务起点相对 ENU）",
        "attitude": "姿态",
        "trajectory_panel": "三维轨迹",
        "recorded": "飞控记录",
        "recorded_pure_ins": "飞控纯惯导",
        "recorded_kf6": "飞控 KF_6",
        "active": "活动数据源",
        "synthetic": "合成测试数据",
        "pre_deploy": "开伞前",
        "post_deploy": "开伞后",
        "start": "任务开始",
        "deploy": "开伞",
        "landing": "着陆",
        "current": "当前位置",
        "source_recorded": "飞控记录",
        "source_recomputed": "离线复算",
        "source_what_if": "假设参数",
        "state_std_quantity": "状态标准差（1σ）",
        "innovation_quantity": "新息",
        "nis_quantity": "归一化新息平方（NIS）",
        "measurement_std_quantity": "量测标准差 sqrt(R)",
        "measurement_update": "量测更新总览",
        "no_valid_updates": "本任务未产生有效 {group}量测更新",
        "no_valid_diagnostics": "未记录有效的 {group} 诊断样本",
        "initial_p_source": "START 使用 INITIAL_STATE.p0_diagonal 构造的对角 P0",
        "full_p_title": "完整协方差矩阵 P 关键帧",
        "full_p_algorithm": "算法",
        "full_p_source": "数据源",
        "full_p_source_recorded": "飞控记录（Recorded）",
        "full_p_source_recomputed": "复算（Recomputed）",
        "full_p_source_what_if": "假设参数（What-if）",
        "full_p_states": "状态向量顺序和物理单位",
        "full_p_rule": (
            "取帧规则：仅使用 P timestamp <= Event timestamp 的最后一个有效样本；"
            "不插值；START 之前无完整 P 时使用 INITIAL_STATE 的 P0 对角阵。"
        ),
        "full_p_event_timestamp": "事件时间戳 [us]",
        "full_p_timestamp": "实际采用的 P 时间戳 [us]",
        "full_p_delta": "时间差（事件 - P）",
        "full_p_matrix": "完整 P 矩阵",
        "full_p_analysis_end": "未找到 LANDING；事件时刻使用分析结束时刻",
        "full_p_event_missing": "日志中没有该事件",
        "full_p_sample_missing": "事件时刻或此前没有有效 P；未使用事件后的样本",
    },
    ExportLanguage.EN: {
        "time": "Mission Time",
        "value": "Value",
        "valid": "Valid",
        "trajectory": "3D Flight Trajectory (Mission-relative ENU)",
        "attitude": "Attitude",
        "trajectory_panel": "3D Trajectory",
        "recorded": "Recorded",
        "recorded_pure_ins": "Recorded Pure INS",
        "recorded_kf6": "Recorded KF_6",
        "active": "Active Source",
        "synthetic": "Synthetic Test Data",
        "pre_deploy": "Pre-deploy",
        "post_deploy": "Post-deploy",
        "start": "Mission Start",
        "deploy": "Deploy",
        "landing": "Landing",
        "current": "Current Position",
        "source_recorded": "Recorded",
        "source_recomputed": "Offline Recomputed",
        "source_what_if": "What-if",
        "state_std_quantity": "State Standard Deviation (1σ)",
        "innovation_quantity": "Innovation",
        "nis_quantity": "Normalized Innovation Squared (NIS)",
        "measurement_std_quantity": "Measurement Standard Deviation sqrt(R)",
        "measurement_update": "Measurement Update Overview",
        "no_valid_updates": "No valid {group} measurement updates were recorded.",
        "no_valid_diagnostics": (
            "No valid {group} diagnostic samples were recorded."
        ),
        "initial_p_source": (
            "START uses the diagonal P0 reconstructed from "
            "INITIAL_STATE.p0_diagonal"
        ),
        "full_p_title": "Full Covariance Matrix P Keyframes",
        "full_p_algorithm": "Algorithm",
        "full_p_source": "Source",
        "full_p_source_recorded": "Recorded",
        "full_p_source_recomputed": "Recomputed",
        "full_p_source_what_if": "What-if",
        "full_p_states": "State vector order and physical units",
        "full_p_rule": (
            "Selection rule: use the last valid sample with P timestamp <= "
            "Event timestamp; no interpolation. If START precedes the first full-P "
            "sample, use the INITIAL_STATE P0 diagonal."
        ),
        "full_p_event_timestamp": "Event timestamp [us]",
        "full_p_timestamp": "Selected P timestamp [us]",
        "full_p_delta": "Time difference (Event - P)",
        "full_p_matrix": "Full P matrix",
        "full_p_analysis_end": "LANDING not found; the analysis end is used as the event time",
        "full_p_event_missing": "The event is not present in the log",
        "full_p_sample_missing": (
            "No valid P exists at or before the event; no post-event sample was used"
        ),
    },
}

_ITEM_LABELS = {
    ExportLanguage.ZH: {
        "overview": "飞行概览",
        "diagnostics": "解析诊断",
        "events": "事件清单",
        "csv": "CSV 数据",
        "full_covariance": "完整协方差矩阵 P 关键帧",
        "trajectory_3d": "三维飞行轨迹",
        "flight_replay_gif": "三维飞行回放 GIF",
        "manifest": "导出清单",
        "failure_report": "导出失败报告",
    },
    ExportLanguage.EN: {
        "overview": "Flight Overview",
        "diagnostics": "Parser Diagnostics",
        "events": "Event List",
        "csv": "CSV Data",
        "full_covariance": "Full Covariance Matrix P Keyframes",
        "trajectory_3d": "3D Flight Trajectory",
        "flight_replay_gif": "3D Flight Replay GIF",
        "manifest": "Export Manifest",
        "failure_report": "Export Failure Report",
    },
}

_COLORS = (
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
_ROCKET_BASE_VERTICES = np.asarray(
    (
        (-0.35, -0.35, 0.0),
        (0.35, -0.35, 0.0),
        (0.35, 0.35, 0.0),
        (-0.35, 0.35, 0.0),
        (0.0, 0.0, 2.2),
    ),
    dtype=np.float64,
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
_EVENT_MISSION_START = 0x03
_EVENT_DEPLOY = 0x29
_EVENT_LANDING = 0x2A
_REPLAY_FRAMES_PER_SECOND = 30
_REPLAY_FINAL_HOLD_FRAME_COUNT = 30
_REPLAY_FINAL_HOLD_DURATION_MS = 1_000
_EXPORT_PROGRESS_SCALE = 1_000
_ATTITUDE_AXIS_LIMIT = 2.5
_ATTITUDE_VIEW_ELEVATION = 18.0
_ATTITUDE_VIEW_AZIMUTH = 35.0
_TRAJECTORY_VIEW_ELEVATION = 20.0
_TRAJECTORY_VIEW_AZIMUTH = 35.0


@dataclass(frozen=True, slots=True)
class _ReplayFrameSample:
    timestamp_us: int
    quaternion: np.ndarray
    current_position: np.ndarray
    current_color: str
    deploy_visible: bool
    landing_visible: bool
    pre_deploy_values: np.ndarray
    post_deploy_values: np.ndarray


@dataclass(slots=True)
class _ReplayTrajectoryArtists:
    pre_deploy_line: Any
    post_deploy_line: Any
    current_marker: Any
    deploy_marker: Any | None
    landing_marker: Any | None


@dataclass(slots=True)
class _ExportProgressTracker:
    context: TaskContext
    total_units: int
    completed_units: int = 0
    last_reported_step: int = -1

    def Unit_Complete(self, code: str, units: int = 1) -> None:
        if units <= 0:
            return
        self.completed_units = min(
            self.completed_units + units,
            max(self.total_units, 1),
        )
        progress = self.completed_units / max(self.total_units, 1)
        step = int(progress * _EXPORT_PROGRESS_SCALE)
        if step <= self.last_reported_step and self.completed_units < self.total_units:
            return
        self.last_reported_step = step
        self.context.Progress_Report(progress, code)

    def Finish(self, code: str) -> None:
        if self.completed_units >= self.total_units and self.last_reported_step >= 1_000:
            return
        self.completed_units = max(self.total_units, 1)
        self.last_reported_step = _EXPORT_PROGRESS_SCALE
        self.context.Progress_Report(1.0, code)


def _PlotColor_Get(index: int) -> str:
    if index < len(_COLORS):
        return _COLORS[index]
    hue = (0.61803398875 * index + 0.13) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.88)
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def _Filename_Sanitize(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.")
    return sanitized[:120] or "channel"


def _Json_Default(value: Any) -> Any:
    if is_dataclass(value):
        # Leave nested immutable values to JSON's default callback; asdict deep-copies
        # mappingproxy fields and fails before Mapping can be serialized.
        return {item.name: getattr(value, item.name) for item in fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


def _Event_Timestamp(dataset: FlightDataset, event_id: int) -> int | None:
    for record in dataset.Records_Get("EVENT"):
        if int(record.payload.get("event_id", -1)) == event_id:
            return int(record.timestamp_us)
    return None


def _Series_Crop(
    series: TimeSeries,
    start_timestamp_us: int,
    end_timestamp_us: int | None = None,
) -> TimeSeries:
    mask = series.timestamp_us >= np.uint64(max(start_timestamp_us, 0))
    if end_timestamp_us is not None:
        mask &= series.timestamp_us <= np.uint64(max(end_timestamp_us, 0))
    return TimeSeries(
        timestamp_us=series.timestamp_us[mask],
        values=np.asarray(series.values)[mask],
        unit=series.unit,
        quantity=series.quantity,
        source=series.source,
        valid=series.valid[mask],
        columns=series.columns,
        metadata=series.metadata,
    )


class FlightExporter:
    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self._registry = registry or builtin_registry()

    def export(
        self,
        dataset: FlightDataset,
        output_directory: Path,
        *,
        options: ExportOptions | None = None,
        algorithm_results: Mapping[str, AlgorithmResult] | None = None,
        replay_store: ReplayResultStore | None = None,
        context: TaskContext | None = None,
    ) -> ExportManifest:
        requested = options or ExportOptions()
        language = self._Language_Resolve(requested.language, requested.ui_language)
        resolved_theme = (
            ExportTheme(requested.ui_theme)
            if requested.theme == ExportTheme.FOLLOW_UI else requested.theme
        )
        task_context = context or TaskContext()
        output = Path(output_directory)
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise FileExistsError(f"export_directory_not_empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        suffix = "_ZH" if language == ExportLanguage.ZH else "_EN"
        files: list[Path] = []
        generated: list[ExportGenerated] = []
        skipped: list[ExportSkipped] = []
        failures: list[ExportFailure] = []
        source_store = self._Store_Prepare(replay_store, algorithm_results or {})
        resolved_source_id = requested.source_id or source_store.ActiveSource_Get().source_id
        store = source_store.Snapshot_Create(resolved_source_id)
        resolver = ChannelResolver(dataset, store)
        mission_bounds = resolver.MissionReplayBounds_Get()
        flight_bounds = FlightDisplayBounds_Get(dataset, mission_bounds)
        trajectory_bounds = resolver.TrajectoryBounds_Get()
        flight_position = resolver.Series_Get("navigation.position_enu")
        flight_trajectory_bounds = (
            TrajectoryBounds_Calculate(flight_position, flight_bounds)
            if flight_position is not None else trajectory_bounds
        )
        channels = self._SourceChannels_Get(resolver)
        if requested.selected_channels:
            selected = set(requested.selected_channels)
            channels = {name: series for name, series in channels.items() if name in selected}
        full_covariance = (
            self._FullCovarianceSelection_Get(resolver)
            if requested.include_full_covariance_keyframes
            else None
        )
        plot_directory = output / f"Plots{suffix}"
        duration = (mission_bounds.end_timestamp_us - mission_bounds.start_timestamp_us) * 1e-6
        pages = ExportPages_Get(duration, requested.page_mode, requested.page_duration,
                                requested.current_range)
        flight_duration = (flight_bounds.end_timestamp_us - flight_bounds.start_timestamp_us) * 1e-6
        selected = ((0.0, flight_duration) if requested.gif_range_mode == "Full" else
                    requested.current_range or (0.0, min(flight_duration, 30.0)))
        selection_duration = selected[1] - selected[0]
        if selected[0] >= flight_duration:
            selected = (max(0.0, flight_duration - selection_duration), flight_duration)
        else:
            selected = (selected[0], min(selected[1], flight_duration))
        gif_bounds = replace(
            flight_bounds,
            start_timestamp_us=flight_bounds.start_timestamp_us + round(selected[0] * 1e6),
            end_timestamp_us=flight_bounds.start_timestamp_us + round(selected[1] * 1e6),
            end_reason=(flight_bounds.end_reason if selected[1] >= flight_duration
                        else MissionReplayEndReason.SOURCE_END),
        )
        gif_metadata = GifMetadata_Get(*selected)
        gif_metadata["analysis_source"] = store.ActiveSource_Get().source_id
        integrity_result = None
        vertical_result = None
        integrity_error = None
        integrity_parameters = {}
        if requested.include_plots and dataset.Records_Get("GNSS_NATIVE"):
            try:
                source = store.ActiveSource_Get()
                entry = store.SourceEntry_Get(source.source_id)
                integrity_parameters = dict(
                    entry.parameters if entry is not None else
                    self._registry.Algorithm_Get("silverstar.algorithm.kf6")
                    .recorded_parameters(dataset)
                )
                integrity_parameters["gnss_integrity_enable"] = 1
                integrity_result = GnssIntegrityStream_Build(
                    dataset, integrity_parameters)
                vertical_result = GnssVerticalConsistency_Build(
                    dataset,
                    max_gap_ms=int(integrity_parameters.get("gnss_integrity_max_gap_ms", 120)),
                )
            except (ValueError, KeyError, TypeError) as error:
                integrity_error = str(error)

        standard_plot_units = (
            self._StandardPlotWorkUnitCount_Get(
                dataset,
                resolver,
                plot_directory,
                suffix,
                language,
                resolved_theme,
            )
            if requested.include_plots
            else 0
        )
        gif_attitude = (
            resolver.Series_Get("attitude.q_nb")
            if requested.include_attitude_gif
            else None
        )
        gif_position = (
            resolver.Series_Get("navigation.position_enu")
            if requested.include_attitude_gif
            else None
        )
        gif_main_frame_count = 0
        if gif_attitude is not None and gif_position is not None:
            deploy_timestamp = _Event_Timestamp(dataset, _EVENT_DEPLOY)
            landing_timestamp = (
                gif_bounds.end_timestamp_us
                if gif_bounds.end_reason == MissionReplayEndReason.LANDING
                else None
            )
            gif_main_frame_count = int(
                self._ReplayFrameTimestamps_Get(
                    gif_attitude,
                    gif_position,
                    gif_bounds.start_timestamp_us,
                    frames_per_second=_REPLAY_FRAMES_PER_SECOND,
                    end_timestamp_us=gif_bounds.end_timestamp_us,
                    key_event_timestamps=tuple(
                        timestamp
                        for timestamp in (
                            gif_bounds.start_timestamp_us,
                            deploy_timestamp,
                            landing_timestamp,
                        )
                        if timestamp is not None
                    ),
                ).size
            )
        gif_frame_units = (
            gif_main_frame_count + _REPLAY_FINAL_HOLD_FRAME_COUNT
            if gif_main_frame_count
            else 0
        )
        total_work_units = (
            int(requested.include_overview)
            + int(requested.include_diagnostics)
            + int(requested.include_events)
            + (len(channels) if requested.include_csv else 0)
            + int(full_covariance is not None)
            + (standard_plot_units + int(requested.include_plots)) * len(pages)
            + (sum(entry.algorithm_id == "silverstar.algorithm.sf6"
                   for entry in store.Entries_Get())
               if requested.include_csv else 0)
            + (3 * len(pages) if integrity_result is not None else 0)
            + int(requested.include_trajectory_3d)
            + gif_frame_units
            + int(requested.include_attitude_gif)
            + 1  # Export manifest.
        )
        progress = _ExportProgressTracker(task_context, total_work_units)

        def item_name(item_id: str, explicit_name: str | None = None) -> str:
            return explicit_name or self._ItemName_Get(item_id, language)

        def failure_add(
            item_id: str,
            localized_name: str,
            exception: Exception,
        ) -> None:
            failure = ExportFailure(
                item_id=item_id,
                localized_name=localized_name,
                exception_type=type(exception).__name__,
                exception_message=str(exception),
            )
            failures.append(failure)
            logging.warning(
                "Export item failed (%s / %s): %s",
                item_id,
                localized_name,
                failure.error,
            )

        def attempt(
            item_id: str,
            path: Path,
            callback: Callable[[], None],
            localized_name: str | None = None,
            progress_code: str = "export.running",
        ) -> None:
            name = item_name(item_id, localized_name)
            try:
                task_context.Cancel_RaiseIfRequested()
                path.parent.mkdir(parents=True, exist_ok=True)
                callback()
                if not path.is_file():
                    raise FileNotFoundError(f"export_output_missing:{path.name}")
                files.append(path)
                generated.append(ExportGenerated(item_id, name, path))
            except TaskCancelledError:
                raise
            except Exception as exc:  # Each product must fail independently.
                failure_add(item_id, name, exc)
            finally:
                progress.Unit_Complete(progress_code)

        def skip(
            item_id: str,
            localized_name: str,
            reason: str,
        ) -> None:
            skipped.append(ExportSkipped(item_id, localized_name, reason))

        failure_report_path = output / f"Export_Failures{suffix}.txt"

        def failure_report_ensure() -> None:
            if not failures:
                return
            name = item_name("failure_report")
            try:
                self._FailureReport_Write(
                    failure_report_path,
                    language,
                    tuple(
                        failure
                        for failure in failures
                        if failure.item_id != "failure_report"
                    ),
                )
                failures[:] = [
                    failure
                    for failure in failures
                    if failure.item_id != "failure_report"
                ]
                if failure_report_path not in files:
                    files.append(failure_report_path)
                    generated.append(
                        ExportGenerated("failure_report", name, failure_report_path)
                    )
            except Exception as exc:
                if not any(
                    failure.item_id == "failure_report" for failure in failures
                ):
                    failure_add("failure_report", name, exc)

        if requested.include_overview:
            path = output / f"Flight_Overview{suffix}.json"
            attempt(
                "overview",
                path,
                lambda: path.write_text(
                    json.dumps(
                        FlightSummary_Build(dataset),
                        default=_Json_Default,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                ),
                item_name("overview"),
            )
        if requested.include_diagnostics:
            path = output / f"Parser_Diagnostics{suffix}.json"
            attempt(
                "diagnostics",
                path,
                lambda: path.write_text(
                    json.dumps(dataset.diagnostics.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                ),
                item_name("diagnostics"),
            )
        if requested.include_events:
            path = output / f"Events{suffix}.csv"
            attempt(
                "events",
                path,
                lambda: self._Events_Write(dataset, path),
                item_name("events"),
            )

        if requested.include_csv:
            csv_directory = output / f"CSV{suffix}"
            csv_directory.mkdir(exist_ok=True)
            for entry in store.Entries_Get():
                if entry.algorithm_id == "silverstar.algorithm.sf6":
                    path = csv_directory / (
                        f"SF6_{_Filename_Sanitize(entry.result_id)}_Replay_Audit{suffix}.json"
                    )
                    attempt(
                        f"sf6_replay_audit:{entry.result_id}", path,
                        lambda p=path, e=entry: p.write_text(json.dumps({
                            "algorithm_id": e.algorithm_id, "mode": e.mode.value,
                            "fidelity": e.fidelity.value, "warnings": list(e.warnings),
                            "parameters": dict(e.parameters), "diagnostics": dict(e.diagnostics),
                        }, ensure_ascii=False, indent=2, default=_Json_Default), encoding="utf-8"),
                        "SF6 replay audit",
                    )
            for channel_id, series in channels.items():
                path = csv_directory / f"{_Filename_Sanitize(channel_id)}{suffix}.csv"
                attempt(
                    f"csv:{channel_id}",
                    path,
                    lambda p=path, c=channel_id, s=series: self._SeriesCsv_Write(
                        dataset, c, s, p
                    ),
                    f"{item_name('csv')} · {channel_id}",
                )

        if requested.include_full_covariance_keyframes:
            if full_covariance is not None:
                source, metadata, specification, series = full_covariance
                path = output / f"{specification.file_stem}{suffix}.txt"
                attempt(
                    f"full_covariance_keyframes:{metadata.plugin_id}:{source.kind.value}",
                    path,
                    lambda: self._FullCovarianceKeyframes_Write(
                        dataset,
                        series,
                        path,
                        language,
                        source,
                        metadata,
                        specification,
                        resolver.MissionReplayBounds_Get(source.source_id),
                    ),
                    (
                        f"{item_name('full_covariance')} · "
                        f"{metadata.display_name}"
                    ),
                )
            else:
                skip(
                    "full_covariance_keyframes",
                    item_name("full_covariance"),
                    "full_covariance_unavailable",
                )

        if requested.include_plots:
            for page_start, page_end in pages:
                task_context.Cancel_RaiseIfRequested()
                self._plot_page_range = (page_start, page_end)
                try:
                    self._StandardPlots_Write(
                        dataset, resolver, PlotDirectory(plot_directory, page_start, page_end),
                        suffix, language, resolved_theme, attempt, skip,
                    )
                    path = plot_directory / "Trajectory2D" / (
                        f"Horizontal_Trajectory_{page_start:010.3f}-{page_end:010.3f}{suffix}.png"
                    )
                    attempt(
                        f"horizontal_trajectory:{page_start:g}-{page_end:g}", path,
                        lambda p=path, a=page_start, b=page_end: self._HorizontalTrajectory_Write(
                            dataset, resolver.Series_Get("navigation.position_enu"), p,
                            language, resolved_theme, flight_bounds, (a, b)),
                        Translator(language.value).Text_Get("horizontal.title"),
                    )
                finally:
                    self._plot_page_range = None

        if integrity_result is not None:
            integrity_dir = output / "GNSSIntegrity"
            for page_start, page_end in pages:
                for kind, name_key in (
                    ("GNSS_Horizontal_Consistency_Error", "export.gnss_integrity.horizontal"),
                    ("GNSS_Vertical_Consistency_Error", "export.gnss_integrity.vertical"),
                    ("GNSS_Receiver_Information", "export.gnss_integrity.receiver"),
                ):
                    interval = f"{page_start:010.3f}-{page_end:010.3f}"
                    path = integrity_dir / kind / f"{kind}_{interval}{suffix}.png"
                    attempt(
                        f"gnss_integrity:{kind}:{interval}", path,
                        lambda p=path, k=kind, a=page_start, b=page_end:
                            self._GnssIntegrityPlot_Write(
                                dataset, integrity_result, k, p, language,
                                resolved_theme, a, b, integrity_parameters,
                                vertical_result,
                            ),
                        Translator(language.value).Text_Get(name_key),
                    )
        elif requested.include_plots and dataset.Records_Get("GNSS_NATIVE"):
            skip("gnss_integrity", "GNSS Integrity", integrity_error or "unavailable")

        if requested.include_trajectory_3d:
            path = output / "Trajectory3D" / f"Trajectory_3D{suffix}.png"
            attempt(
                "trajectory_3d",
                path,
                lambda: self._Trajectory_Write(
                    dataset,
                    self._Series_Require(
                        resolver.Series_Get("navigation.position_enu"),
                        "navigation.position_enu",
                    ),
                    path,
                    language,
                    resolved_theme,
                    mission_bounds=flight_bounds,
                    trajectory_bounds=flight_trajectory_bounds,
                ),
                item_name("trajectory_3d"),
            )
        if requested.include_attitude_gif:
            path = output / "GIF" / f"Flight_Replay{suffix}.gif"
            attempt(
                "flight_replay_gif",
                path,
                lambda: self._FlightReplayGif_Write(
                    dataset,
                    self._Series_Require(
                        gif_attitude,
                        "attitude.q_nb",
                    ),
                    self._Series_Require(
                        gif_position,
                        "navigation.position_enu",
                    ),
                    path,
                    language,
                    resolved_theme,
                    progress,
                    mission_bounds=gif_bounds,
                    trajectory_bounds=flight_trajectory_bounds,
                ),
                item_name("flight_replay_gif"),
            )

            metadata_path = path.with_suffix(".json")
            if path.is_file():
                metadata_path.write_text(json.dumps(gif_metadata, indent=2), encoding="utf-8")
                files.append(metadata_path)
                generated.append(ExportGenerated("gif_metadata", "GIF", metadata_path))

        failure_report_ensure()
        manifest_path = output / f"Export_Manifest{suffix}.json"
        manifest_name = item_name("manifest")
        prospective_generated = (
            *generated,
            ExportGenerated("manifest", manifest_name, manifest_path),
        )
        try:
            task_context.Cancel_RaiseIfRequested()
            self._Manifest_Write(
                manifest_path,
                output,
                dataset,
                prospective_generated,
                skipped,
                failures,
                language,
                resolved_theme,
                requested.theme,
                store,
                requested,
                tuple(channels),
                tuple(pages),
                selected,
            )
            files.append(manifest_path)
            generated.append(
                ExportGenerated("manifest", manifest_name, manifest_path)
            )
        except Exception as exc:
            failure_add("manifest", manifest_name, exc)
            failure_report_ensure()
        finally:
            progress.Unit_Complete("export.running")
        progress.Finish("export.running")
        return ExportManifest(
            output,
            tuple(files),
            language,
            resolved_theme,
            tuple(failures),
            tuple(generated),
            tuple(skipped),
        )

    @staticmethod
    def _SourceChannels_Get(resolver: ChannelResolver) -> dict[str, TimeSeries]:
        source = resolver.store.ActiveSource_Get()
        channels = resolver.ExplorerChannels_Get()
        if source.kind != AnalysisSourceKind.RECORDED:
            return {
                name: series for name, series in channels.items()
                if ".recorded." not in name
            }
        recorded_namespace = resolver.RecordedNavigationSource_Get()
        if recorded_namespace == "KF_6":
            excluded = "pure_ins.recorded."
        elif recorded_namespace == "Pure INS":
            excluded = "kf6.recorded."
        else:
            excluded = ""
        return {
            name: series for name, series in channels.items()
            if not excluded or not name.startswith(excluded)
        }

    @staticmethod
    def _Language_Resolve(language: ExportLanguage, ui_language: str) -> ExportLanguage:
        if language != ExportLanguage.FOLLOW_UI:
            return language
        return ExportLanguage.EN if ui_language == ExportLanguage.EN.value else ExportLanguage.ZH

    @staticmethod
    def _Store_Prepare(
        replay_store: ReplayResultStore | None,
        algorithm_results: Mapping[str, AlgorithmResult],
    ) -> ReplayResultStore:
        if replay_store is not None:
            return replay_store
        store = ReplayResultStore()
        latest_source = ReplayResultStore.RECORDED_SOURCE_ID
        for result_name, result in algorithm_results.items():
            entry = store.Result_Add(result, algorithm_name=result_name)
            latest_source = entry.source_id
        store.ActiveSource_Set(latest_source)
        return store

    @staticmethod
    def _Series_Require(series: TimeSeries | None, channel_id: str) -> TimeSeries:
        if series is None or series.count == 0:
            raise ValueError(f"channel_unavailable:{channel_id}")
        return series

    @staticmethod
    def _SeriesCsv_Write(
        dataset: FlightDataset,
        channel_id: str,
        series: TimeSeries,
        path: Path,
    ) -> None:
        values = np.asarray(series.values)
        columns = series.columns or (
            tuple(f"value_{index}" for index in range(values.shape[1]))
            if values.ndim == 2
            else ("value",)
        )
        start = dataset.start_timestamp_us or (int(series.timestamp_us[0]) if series.count else 0)
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(
                [
                    f"# channel={channel_id}",
                    f"unit={series.unit}",
                    f"quantity={series.quantity}",
                    f"source={series.source}",
                    f"synthetic={bool(dataset.metadata.get('synthetic', False))}",
                ]
            )
            writer.writerow(["timestamp_us", "time_from_start_s", *columns, "valid"])
            for index, timestamp in enumerate(series.timestamp_us):
                sample = values[index]
                sample_values = sample.tolist() if values.ndim == 2 else [sample.item()]
                writer.writerow(
                    [
                        int(timestamp),
                        f"{(int(timestamp) - start) * 1.0e-6:.9f}",
                        *sample_values,
                        int(series.valid[index]),
                    ]
                )

    @staticmethod
    def _Events_Write(dataset: FlightDataset, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(
                ["timestamp_us", "record_sequence", "event_id", "event_name", "arg0", "arg1"]
            )
            for record in dataset.Records_Get("EVENT"):
                writer.writerow(
                    [
                        record.timestamp_us,
                        record.record_sequence,
                        int(record.payload["event_id"]),
                        record.payload["event_name"],
                        int(record.payload["arg0"]),
                        int(record.payload["arg1"]),
                    ]
                )

    @staticmethod
    def _ItemName_Get(item_id: str, language: ExportLanguage) -> str:
        labels = _ITEM_LABELS[language]
        if item_id.startswith("csv:"):
            return f"{labels['csv']} · {item_id.partition(':')[2]}"
        if item_id.startswith("full_covariance"):
            return labels["full_covariance"]
        if item_id.startswith("standard_plot:"):
            return item_id.partition(":")[2].replace("_", " ")
        return labels.get(item_id, item_id)

    @staticmethod
    def _FailureReport_Write(
        path: Path,
        language: ExportLanguage,
        failures: tuple[ExportFailure, ...],
    ) -> None:
        lines = ["SilverStar_FLP Export Failures", "=" * 36]
        type_label = "类型" if language == ExportLanguage.ZH else "Type"
        message_label = "信息" if language == ExportLanguage.ZH else "Message"
        name_label = "项目" if language == ExportLanguage.ZH else "Item"
        for failure in failures:
            lines.extend(
                (
                    "",
                    failure.item_id,
                    f"{name_label}: {failure.localized_name}",
                    f"{type_label}: {failure.exception_type}",
                    f"{message_label}: {failure.exception_message}",
                )
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _Manifest_Write(
        self,
        path: Path,
        output: Path,
        dataset: FlightDataset,
        generated: tuple[ExportGenerated, ...],
        skipped: list[ExportSkipped],
        failures: list[ExportFailure],
        language: ExportLanguage,
        theme: ExportTheme,
        theme_mode: ExportTheme,
        store: ReplayResultStore,
        options: ExportOptions,
        exported_channel_ids: tuple[str, ...],
        page_ranges: tuple[tuple[float, float], ...],
        gif_range: tuple[float, float],
    ) -> None:
        active = store.ActiveSource_Get()
        source_hash = hashlib.sha256()
        with dataset.source_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                source_hash.update(chunk)
        semantic_context = dataset.semantic_context
        semantic_payload = (
            semantic_context.ToDict() if semantic_context is not None else None
        )
        replay_payload = []
        for entry in store.Entries_Get():
            firmware_member = False
            recorded_output_available = False
            try:
                plugin = self._registry.Algorithm_Get(entry.algorithm_id)
                firmware_member = plugin.FirmwareMember_Is(dataset)
                recorded_output_available = plugin.RecordedOutput_IsAvailable(dataset)
                input_contract = {
                    "required_records": plugin.metadata.required_records,
                    "optional_records": plugin.metadata.optional_records,
                    "required_semantic_roles": (
                        plugin.metadata.required_semantic_roles
                    ),
                    "optional_semantic_roles": (
                        plugin.metadata.optional_semantic_roles
                    ),
                    "cadence": dict(plugin.metadata.cadence_contract),
                    "gap_tolerance": dict(
                        plugin.metadata.gap_tolerance_contract
                    ),
                    "parameter_sources": dict(
                        plugin.metadata.parameter_source_contract
                    ),
                    "coordinate_frame": dict(
                        plugin.metadata.coordinate_frame_contract
                    ),
                    "exact_validation_reference": (
                        plugin.metadata.exact_validation_reference or None
                    ),
                }
            except KeyError:
                input_contract = None
            replay_payload.append(
                {
                    "result_id": entry.result_id,
                    "source_id": entry.source_id,
                    "algorithm_id": entry.algorithm_id,
                    "algorithm_version": entry.algorithm_version,
                    "mode": entry.mode.value,
                    "provenance": entry.result.provenance,
                    "input_source": entry.input_source,
                    "actual_parameters": dict(entry.parameters),
                    "offline_diagnostics": entry.diagnostics.get("offline_diagnostics"),
                    "parameter_schema_identity": entry.diagnostics.get("parameter_schema_identity"),
                    "parameter_metadata": entry.diagnostics.get("parameter_metadata", {}),
                    "config_source": entry.diagnostics.get("config_source"),
                    "fidelity": entry.fidelity.value,
                    "warnings": list(entry.warnings),
                    "firmware_member": firmware_member,
                    "recorded_output_available": recorded_output_available,
                    "channel_ids": sorted(entry.channels),
                    "input_contract": input_contract,
                }
            )
        configured_streams = []
        if semantic_context is not None:
            for stream in semantic_context.logging_streams:
                raw_record_name = str(stream.get("record", ""))
                prefix = "FLIGHT_LOG_RECORD_"
                record_name = (
                    raw_record_name[len(prefix) :]
                    if raw_record_name.startswith(prefix)
                    else raw_record_name
                )
                configured_streams.append(
                    {
                        **dict(stream),
                        "record_name": record_name,
                        "recorded_sample_count": len(
                            dataset.Records_Get(record_name)
                        ),
                    }
                )
        resolver = ChannelResolver(dataset, store)
        explorer_channels = resolver.ExplorerChannels_Get()
        channel_provenance: dict[str, Any] = {}
        for channel_id in exported_channel_ids:
            series = explorer_channels.get(channel_id)
            if series is None:
                continue
            raw_channel_id = (
                semantic_context.StableRole_Get(channel_id)
                if semantic_context is not None
                else None
            )
            channel_provenance[channel_id] = {
                "source": series.source,
                "record_name": series.metadata.get("record_name"),
                "field_name": series.metadata.get("field_name"),
                "stable_role": channel_id if raw_channel_id is not None else None,
                "raw_channel_id": raw_channel_id,
                "descriptor_id": series.metadata.get("descriptor_id"),
                "physical_device_id": series.metadata.get(
                    "physical_device_id"
                ),
                "capability_class": series.metadata.get("capability_class"),
                "instance_id": series.metadata.get("instance_id"),
                "quantity": series.quantity,
                "unit": series.unit,
                "sample_count": series.count,
                "valid_sample_count": int(np.count_nonzero(series.valid)),
                "timestamps": "recorded_per_channel",
                "columns": list(series.columns),
                "cadence_quality": TimeSeriesGapSummary_Get(series),
            }
        summary = FlightSummary_Build(dataset)
        generated_payload = [
            {
                "item_id": item.item_id,
                "localized_name": item.localized_name,
                "path": str(item.path.relative_to(output)),
            }
            for item in generated
        ]
        skipped_payload = [asdict(item) for item in skipped]
        failure_payload = [asdict(item) for item in failures]
        payload = {
            "source_log": {
                "path": str(dataset.source_path),
                "size_bytes": dataset.file_size,
                "sha256": source_hash.hexdigest(),
            },
            "decoder_profile": (
                {
                    **semantic_payload["package_identity"],
                    "match_mode": "exact_generation_profile",
                }
                if semantic_payload is not None
                else None
            ),
            "project": (
                semantic_payload["package_identity"]["project_name"]
                if semantic_payload is not None
                else None
            ),
            "firmware": (
                {
                    "version": semantic_payload["package_identity"]["firmware_version"],
                    "commit": semantic_payload["package_identity"]["firmware_commit"],
                    "algorithm_components": semantic_payload["firmware_algorithm_ids"],
                    "algorithm_parameters": semantic_payload["algorithm_parameters"],
                }
                if semantic_payload is not None
                else None
            ),
            "hardware": semantic_payload["hardware"] if semantic_payload is not None else None,
            "protocols": semantic_payload["protocols"] if semantic_payload is not None else None,
            "calibration": (
                semantic_payload["calibration"]
                if semantic_payload is not None
                else None
            ),
            "alignment": asdict(summary.alignment),
            "gnss_usability": asdict(summary.gnss),
            "data_quality": (
                dataset.data_quality.ToDict()
                if dataset.data_quality is not None
                else None
            ),
            "parser_diagnostics": dataset.diagnostics.to_dict(),
            "configured_streams": configured_streams,
            "stable_aliases": (
                semantic_payload["stable_aliases"]
                if semantic_payload is not None
                else {}
            ),
            "exported_channel_provenance": channel_provenance,
            "replay_results": replay_payload,
            "language": language.value,
            "theme": theme.value,
            "theme_mode": theme_mode.value,
            "resolved_theme": theme.value,
            "firmware_gnss_integrity_revision": (
                semantic_context.raw_metadata.get("metadata_declarations", {}).get(
                    "navigation_replay", {}).get("gnss_integrity_revision", 0)
                if semantic_context is not None else None
            ),
            "requested_time_range": {
                "page_mode": options.page_mode,
                "page_duration_s": options.page_duration,
                "current_view_s": options.current_range,
                "gif_range_mode": options.gif_range_mode,
            },
            "resolved_time_range": {
                "pages_s": page_ranges,
                "gif_s": gif_range,
            },
            "requested_topics": {
                "overview": options.include_overview,
                "diagnostics": options.include_diagnostics,
                "events": options.include_events,
                "csv": options.include_csv,
                "full_covariance_keyframes": options.include_full_covariance_keyframes,
                "plots": options.include_plots,
                "trajectory_3d": options.include_trajectory_3d,
                "attitude_gif": options.include_attitude_gif,
                "selected_channels": options.selected_channels,
            },
            "resolved_topics": tuple(item["item_id"] for item in generated_payload),
            "requested_source_mode": options.source_mode,
            "requested_source_id": (
                options.source_id if options.source_mode == "explicit" else None
            ),
            "resolved_source_id": active.source_id,
            "resolved_result_id": active.result_id,
            "active_analysis_source": active.source_id,
            "active_source_kind": active.kind.value,
            "generated": generated_payload,
            "skipped": skipped_payload,
            "failed": failure_payload,
            "files": [item["path"] for item in generated_payload],
            "failures": failure_payload,
        }
        path.write_text(
            json.dumps(payload, default=_Json_Default, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _Plot_Configure(theme: ExportTheme) -> tuple[str, str, str]:
        if theme == ExportTheme.DARK:
            return "#0B1220", "#E5E7EB", "#334155"
        return "#FFFFFF", "#111827", "#CBD5E1"

    @staticmethod
    def _Matplotlib_Configure() -> None:
        import matplotlib

        matplotlib.use("Agg")
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False

    def _Axes_Style(self, figure: Any, axis: Any, theme: ExportTheme) -> None:
        background, foreground, grid = self._Plot_Configure(theme)
        figure.patch.set_facecolor(background)
        axis.set_facecolor(background)
        axis.tick_params(colors=foreground)
        axis.grid(True, color=grid, alpha=0.32)
        for spine in axis.spines.values():
            spine.set_color(foreground)

    @staticmethod
    def _Time_Get(dataset: FlightDataset, series: TimeSeries) -> np.ndarray:
        start = dataset.start_timestamp_us or int(series.timestamp_us[0])
        return (series.timestamp_us.astype(np.float64) - start) * 1.0e-6

    def _TimePage_Apply(self, figure) -> None:
        interval = getattr(self, "_plot_page_range", None)
        if interval is None:
            return
        for axis in figure.axes:
            if getattr(axis, "name", "") == "3d":
                continue
            low, high = interval
            for line in axis.lines:
                if line.get_transform() != axis.transData:
                    continue  # Threshold lines use blended axes coordinates.
                x = np.asarray(line.get_xdata(), dtype=float)
                y = np.asarray(line.get_ydata(), dtype=float)
                if x.size != y.size:
                    continue
                keep = (x >= low) & (x <= high)
                view_x, view_y = PlotArrays_Get(x[keep], y[keep])
                line.set_data(view_x, view_y)
            axis.relim()
            axis.autoscale_view(scalex=False, scaley=True)
            axis.set_xlim(low, max(high, low + .001))

    def _SeriesPlot_Write(
        self,
        dataset: FlightDataset,
        channel_id: str,
        series: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        metadata = ChannelDisplayMetadata_Get(channel_id, series)
        background, foreground, _ = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        self._Axes_Style(figure, axis, theme)
        time = self._Time_Get(dataset, series)
        values = np.asarray(series.values, dtype=np.float64)
        values = values.copy()
        if values.ndim == 1:
            values[~series.valid] = np.nan
            axis.plot(time, values, color=_PlotColor_Get(0), linewidth=1.15)
        else:
            values[~series.valid, :] = np.nan
            for index in range(values.shape[1]):
                raw_label = series.columns[index] if series.columns else str(index)
                axis.plot(
                    time,
                    values[:, index],
                    color=_PlotColor_Get(index),
                    linewidth=1.05,
                    label=ComponentLabel_Get(raw_label, language.value),
                )
            axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.82)
        labels = _LABELS[language]
        title = metadata.Title_Get(language.value)
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" · {labels['synthetic']}"
        axis.set_title(title, color=foreground)
        axis.set_xlabel(f"{labels['time']} (s)", color=foreground)
        quantity = metadata.Quantity_Get(language.value)
        unit = "" if series.unit in ("", "1", "enum", "bitmask") else f" [{series.unit}]"
        axis.set_ylabel(f"{quantity}{unit}", color=foreground)
        figure.tight_layout()
        self._TimePage_Apply(figure)
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _MultiSeriesPlot_Write(
        self,
        dataset: FlightDataset,
        layers: tuple[tuple[TimeSeries, str, str], ...],
        path: Path,
        title: str,
        ylabel: str,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        end_timestamp_us: int | None = None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        self._Axes_Style(figure, axis, theme)
        color_index = 0
        plotted = 0
        start = dataset.start_timestamp_us or 0
        for series, prefix, line_style in layers:
            cropped = _Series_Crop(series, start, end_timestamp_us)
            if cropped.count == 0:
                continue
            time = self._Time_Get(dataset, cropped)
            values = np.asarray(cropped.values, dtype=np.float64)
            values = values[:, None] if values.ndim == 1 else values
            values = values.copy()
            values[~cropped.valid, :] = np.nan
            breaks = tuple(
                (stamp - start) * 1e-6
                for stamp in cropped.metadata.get("discontinuity_timestamps_us", ())
            )
            time, values = PlotArrays_Get(time, values, breaks=breaks, budget=max(len(time), 6000))
            for index in range(values.shape[1]):
                component = cropped.columns[index] if cropped.columns else ""
                component = ComponentLabel_Get(component, language.value)
                label = " · ".join(item for item in (prefix, component) if item)
                axis.plot(
                    time,
                    values[:, index],
                    color=_PlotColor_Get(color_index),
                    linestyle=line_style,
                    linewidth=1.05,
                    label=label,
                )
                color_index += 1
                plotted += 1
        if plotted == 0:
            raise ValueError("no_post_start_samples")
        axis.set_title(title, color=foreground)
        axis.set_xlabel(f"{_LABELS[language]['time']} (s)", color=foreground)
        axis.set_ylabel(ylabel, color=foreground)
        axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.82, ncol=2)
        figure.tight_layout()
        self._TimePage_Apply(figure)
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _FullCovarianceSpecifications_Get(
        self,
    ) -> tuple[tuple[AlgorithmMetadata, FullCovarianceSpec], ...]:
        specifications: list[tuple[AlgorithmMetadata, FullCovarianceSpec]] = []
        for plugin in self._registry.algorithms:
            visualization = plugin.metadata.estimator_visualization
            if visualization is not None and visualization.full_covariance is not None:
                specifications.append(
                    (plugin.metadata, visualization.full_covariance)
                )
        return tuple(specifications)

    def _FullCovarianceChannel_Is(self, channel_id: str) -> bool:
        stable_id = channel_id.rsplit(" / ", 1)[-1]
        stable_id = stable_id.replace(".recorded.", ".", 1)
        return any(
            stable_id == specification.channel_id
            for _, specification in self._FullCovarianceSpecifications_Get()
        )

    def _FullCovarianceSelection_Get(
        self,
        resolver: ChannelResolver,
    ) -> tuple[
        AnalysisSource,
        AlgorithmMetadata,
        FullCovarianceSpec,
        TimeSeries,
    ] | None:
        specifications = self._FullCovarianceSpecifications_Get()
        by_algorithm = {
            metadata.plugin_id: (metadata, specification)
            for metadata, specification in specifications
        }
        sources = resolver.EstimatorSources_Get(tuple(by_algorithm))
        active = resolver.store.ActiveSource_Get()
        ordered: list[AnalysisSource] = []
        ordered.extend(
            source for source in sources if source.source_id == active.source_id
        )
        for source in ordered:
            if source.algorithm_id is None:
                continue
            metadata_and_specification = by_algorithm.get(source.algorithm_id)
            if metadata_and_specification is None:
                continue
            metadata, specification = metadata_and_specification
            series = resolver.Series_Get(specification.channel_id, source.source_id)
            if series is not None and series.count:
                return source, metadata, specification, series
        return None

    @staticmethod
    def _FullCovarianceMatrix_Get(
        sample: np.ndarray,
        specification: FullCovarianceSpec,
    ) -> np.ndarray:
        dimension = len(specification.state_symbols)
        values = np.asarray(sample, dtype=np.float64)
        if specification.storage == "full_matrix":
            if values.size != dimension * dimension:
                raise ValueError("full_covariance_matrix_size_mismatch")
            return values.reshape(dimension, dimension)
        expected = dimension * (dimension + 1) // 2
        flat = values.reshape(-1)
        if flat.size != expected:
            raise ValueError("full_covariance_upper_triangle_size_mismatch")
        matrix = np.empty((dimension, dimension), dtype=np.float64)
        value_index = 0
        for row in range(dimension):
            for column in range(row, dimension):
                matrix[row, column] = flat[value_index]
                matrix[column, row] = flat[value_index]
                value_index += 1
        return matrix

    @staticmethod
    def _FullCovarianceKeyframeIndex_Get(
        series: TimeSeries,
        event_timestamp_us: int,
    ) -> int | None:
        limit = int(
            np.searchsorted(
                series.timestamp_us,
                np.uint64(max(event_timestamp_us, 0)),
                side="right",
            )
        )
        if limit == 0:
            return None
        values = np.asarray(series.values).reshape(series.count, -1)
        eligible = series.valid[:limit] & np.all(np.isfinite(values[:limit]), axis=1)
        indices = np.flatnonzero(eligible)
        return int(indices[-1]) if indices.size else None

    @staticmethod
    def _InitialCovariance_Get(
        dataset: FlightDataset,
        event_timestamp_us: int,
        specification: FullCovarianceSpec,
    ) -> tuple[int, np.ndarray] | None:
        if (
            not specification.initial_record_name
            or not specification.initial_diagonal_field
        ):
            return None
        dimension = len(specification.state_symbols)
        for record in reversed(
            dataset.Records_Get(specification.initial_record_name)
        ):
            if record.timestamp_us > event_timestamp_us:
                continue
            diagonal = np.asarray(
                record.payload.get(specification.initial_diagonal_field, ()),
                dtype=np.float64,
            ).reshape(-1)
            if diagonal.size != dimension or not np.all(np.isfinite(diagonal)):
                continue
            return int(record.timestamp_us), np.diag(diagonal)
        return None

    def _FullCovarianceKeyframes_Write(
        self,
        dataset: FlightDataset,
        series: TimeSeries,
        path: Path,
        language: ExportLanguage,
        source: AnalysisSource,
        metadata: AlgorithmMetadata,
        specification: FullCovarianceSpec,
        mission_bounds: MissionReplayBounds,
    ) -> None:
        labels = _LABELS[language]
        source_label = (
            self._SourceLabel_Get(source, language) if source.analysis_only
            else labels[f"full_p_source_{source.kind.value}"]
        )
        dimension = len(specification.state_symbols)
        landing_timestamp = _Event_Timestamp(dataset, _EVENT_LANDING)
        events = (
            ("START", mission_bounds.start_timestamp_us, None),
            (
                "PARACHUTE_DEPLOY",
                _Event_Timestamp(dataset, _EVENT_DEPLOY),
                None,
            ),
            (
                "LANDING",
                (
                    landing_timestamp
                    if landing_timestamp is not None
                    else mission_bounds.end_timestamp_us
                ),
                labels["full_p_analysis_end"] if landing_timestamp is None else None,
            ),
        )
        lines = [
            labels["full_p_title"],
            "=" * 72,
            f"{labels['full_p_algorithm']}: {metadata.display_name} ({metadata.plugin_id})",
            f"{labels['full_p_source']}: {source_label}",
            f"{labels['full_p_states']}:",
        ]
        lines.extend(
            f"  {index}: {symbol} [{unit}]"
            for index, (symbol, unit) in enumerate(
                zip(
                    specification.state_symbols,
                    specification.state_units,
                    strict=True,
                )
            )
        )
        lines.extend(("", labels["full_p_rule"]))
        for event_name, event_timestamp, note in events:
            lines.extend(("", f"[{event_name}]"))
            if note is not None:
                lines.append(note)
            if event_timestamp is None:
                lines.extend(
                    (
                        f"{labels['full_p_event_timestamp']}: N/A",
                        f"{labels['full_p_timestamp']}: N/A",
                        f"{labels['full_p_delta']}: N/A",
                        f"{labels['full_p_matrix']} ({dimension} x {dimension}): N/A",
                        labels["full_p_event_missing"],
                    )
                )
                continue
            event_timestamp = int(event_timestamp)
            lines.append(
                f"{labels['full_p_event_timestamp']}: {event_timestamp}"
            )
            sample_index = self._FullCovarianceKeyframeIndex_Get(
                series,
                event_timestamp,
            )
            initial = (
                self._InitialCovariance_Get(
                    dataset,
                    event_timestamp,
                    specification,
                )
                if event_name == "START" and sample_index is None
                else None
            )
            if sample_index is None and initial is None:
                lines.extend(
                    (
                        f"{labels['full_p_timestamp']}: N/A",
                        f"{labels['full_p_delta']}: N/A",
                        f"{labels['full_p_matrix']} ({dimension} x {dimension}): N/A",
                        labels["full_p_sample_missing"],
                    )
                )
                continue
            if initial is not None:
                p_timestamp, matrix = initial
                lines.append(labels["initial_p_source"])
            else:
                assert sample_index is not None
                p_timestamp = int(series.timestamp_us[sample_index])
                matrix = self._FullCovarianceMatrix_Get(
                    np.asarray(series.values[sample_index]),
                    specification,
                )
            difference_us = event_timestamp - p_timestamp
            lines.extend(
                (
                    f"{labels['full_p_timestamp']}: {p_timestamp}",
                    f"{labels['full_p_delta']}: {difference_us} us "
                    f"({difference_us * 1.0e-6:.9f} s)",
                    f"{labels['full_p_matrix']} ({dimension} x {dimension}):",
                )
            )
            lines.extend(
                "  " + " ".join(f"{float(value):.17e}" for value in row)
                for row in matrix
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _EstimatorSelection_Get(
        self,
        resolver: ChannelResolver,
    ) -> tuple[
        AnalysisSource,
        AlgorithmMetadata,
        EstimatorVisualizationSpec,
    ] | None:
        metadata_by_id = {
            plugin.metadata.plugin_id: plugin.metadata
            for plugin in self._registry.algorithms
            if plugin.metadata.estimator_visualization is not None
        }
        sources = resolver.EstimatorSources_Get(tuple(metadata_by_id))
        sources = tuple(source for source in sources
                        if source.source_id == resolver.store.ActiveSource_Get().source_id)
        active_id = resolver.store.ActiveSource_Get().source_id

        def source_score(source: AnalysisSource) -> int:
            if source.algorithm_id is None:
                return -1
            metadata = metadata_by_id.get(source.algorithm_id)
            if metadata is None or metadata.estimator_visualization is None:
                return -1
            channels = [
                group.covariance_channel
                for group in metadata.estimator_visualization.state_groups
            ]
            for group in metadata.estimator_visualization.measurement_groups:
                channels.extend(
                    (
                        group.innovation_channel,
                        group.nis_channel,
                        group.effective_r_channel,
                        group.update_result_channel,
                    )
                )
            return sum(
                bool(channel_id)
                and resolver.Series_Get(channel_id, source.source_id) is not None
                for channel_id in channels
            )

        ordered = sorted(
            sources,
            key=lambda source: (
                source.source_id == active_id,
                source.kind == AnalysisSourceKind.RECORDED,
                source_score(source),
            ),
            reverse=True,
        )
        for source in ordered:
            if source.algorithm_id is None:
                continue
            metadata = metadata_by_id.get(source.algorithm_id)
            if metadata is None or metadata.estimator_visualization is None:
                continue
            return source, metadata, metadata.estimator_visualization
        return None

    def _SourceParameters_Get(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        source: AnalysisSource,
    ) -> Mapping[str, Any]:
        if source.algorithm_id is None:
            return {}
        if source.kind == AnalysisSourceKind.RECORDED:
            try:
                return self._registry.Algorithm_Get(
                    source.algorithm_id
                ).recorded_parameters(dataset)
            except (KeyError, TypeError, ValueError):
                return {}
        entry = resolver.store.SourceEntry_Get(source.source_id)
        return entry.parameters if entry is not None else {}

    @staticmethod
    def _SourceLabel_Get(
        source: AnalysisSource,
        language: ExportLanguage,
    ) -> str:
        if source.analysis_only:
            return "仅离线诊断" if language == ExportLanguage.ZH else "Analysis-only"
        return _LABELS[language][f"source_{source.kind.value}"]

    @staticmethod
    def _SourceFileStem_Get(source: AnalysisSource) -> str:
        return {
            AnalysisSourceKind.RECORDED: "Recorded",
            AnalysisSourceKind.RECOMPUTED: "Recomputed",
            AnalysisSourceKind.WHAT_IF: "What_If",
        }[source.kind]

    @staticmethod
    def _AlgorithmFileStem_Get(metadata: AlgorithmMetadata) -> str:
        return _Filename_Sanitize(metadata.display_name.replace("_", ""))

    @staticmethod
    def _GroupFileStem_Get(group_id: str, configured_stem: str) -> str:
        if configured_stem:
            return _Filename_Sanitize(configured_stem)
        return "_".join(
            part.upper() if part.lower() == "gnss" else part.title()
            for part in group_id.split("_")
            if part
        )

    @staticmethod
    def _GroupLabel_Get(
        group_id: str,
        label_key: str,
        language: ExportLanguage,
    ) -> str:
        translated = Translator(language.value).Text_Get(label_key)
        if translated != label_key:
            return translated
        return group_id.replace("_", " ").title()

    @staticmethod
    def _SeriesComponents_Select(
        series: TimeSeries | None,
        indices: tuple[int, ...],
        columns: tuple[str, ...],
    ) -> TimeSeries | None:
        if series is None or series.count == 0:
            return None
        values = np.asarray(series.values, dtype=np.float64)
        values = values[:, None] if values.ndim == 1 else values
        if not indices or max(indices) >= values.shape[1]:
            return None
        selected = values[:, indices]
        return TimeSeries(
            timestamp_us=series.timestamp_us,
            values=selected,
            unit=series.unit,
            quantity=series.quantity,
            source=series.source,
            valid=series.valid.copy(),
            columns=columns,
            metadata=series.metadata,
        )

    @classmethod
    def _SeriesColumn_Select(
        cls,
        series: TimeSeries | None,
        index: int,
        column: str,
    ) -> TimeSeries | None:
        return cls._SeriesComponents_Select(series, (index,), (column,))

    @classmethod
    def _StateStandardDeviationSeries_Get(
        cls,
        resolver: ChannelResolver,
        source_id: str,
        group: StateGroupSpec,
    ) -> TimeSeries | None:
        selected = cls._SeriesComponents_Select(
            resolver.Series_Get(group.covariance_channel, source_id),
            group.covariance_diagonal_indices,
            group.component_names,
        )
        if selected is None:
            return None
        values = np.asarray(selected.values, dtype=np.float64).copy()
        values[values < 0.0] = np.nan
        values = np.sqrt(values)
        return TimeSeries(
            timestamp_us=selected.timestamp_us,
            values=values,
            unit=group.unit,
            quantity="state_standard_deviation_1sigma",
            source=selected.source,
            valid=selected.valid & np.all(np.isfinite(values), axis=1),
            columns=group.component_names,
            metadata=selected.metadata,
        )

    @staticmethod
    def _MeasurementConfigured_Check(
        dataset: FlightDataset,
        group: MeasurementGroupSpec,
    ) -> bool:
        records_present = any(
            dataset.Records_Get(record_name)
            for record_name in group.measurement_record_names
        )
        if records_present:
            return True
        configurations = dataset.Records_Get("SYSTEM_CONFIG")
        evidence_seen = False
        for record in configurations:
            for field_name in group.configuration_fields:
                if field_name not in record.payload:
                    continue
                evidence_seen = True
                try:
                    if float(record.payload[field_name]) > 0.0:
                        return True
                except (TypeError, ValueError):
                    if bool(record.payload[field_name]):
                        return True
            provider_ids = record.payload.get("provider_ids")
            if provider_ids is None:
                continue
            for index in group.configuration_provider_indices:
                if index >= len(provider_ids):
                    continue
                evidence_seen = True
                if int(provider_ids[index]) != 0:
                    return True
        has_configuration_hints = bool(
            group.configuration_fields
            or group.configuration_provider_indices
            or group.measurement_record_names
        )
        return not (has_configuration_hints and evidence_seen)

    @staticmethod
    def _ValidFiniteMask_Get(series: TimeSeries) -> np.ndarray:
        values = np.asarray(series.values, dtype=np.float64)
        finite = (
            np.isfinite(values)
            if values.ndim == 1
            else np.all(np.isfinite(values), axis=1)
        )
        return series.valid & finite

    def _MeasurementHasValidUpdates_Check(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        source: AnalysisSource,
        group: MeasurementGroupSpec,
    ) -> bool:
        bounds = resolver.MissionReplayBounds_Get(source.source_id)
        attempt = resolver.Series_Get(group.attempt_mask_channel, source.source_id)
        if attempt is not None and attempt.count:
            values = np.asarray(attempt.values, dtype=np.float64).reshape(
                attempt.count,
                -1,
            )[:, 0]
            mask = self._ValidFiniteMask_Get(attempt)
            mask &= attempt.timestamp_us >= np.uint64(bounds.start_timestamp_us)
            mask &= attempt.timestamp_us <= np.uint64(bounds.end_timestamp_us)
            if group.attempt_mask_bit:
                integer_values = np.zeros(values.shape, dtype=np.int64)
                integer_values[mask] = values[mask].astype(np.int64)
                mask &= (integer_values & group.attempt_mask_bit) != 0
            return bool(np.any(mask))
        if group.measurement_validity_channel:
            measurement = dataset.Series_Get(group.measurement_validity_channel)
            if measurement is None or measurement.count == 0:
                return False
            mask = self._ValidFiniteMask_Get(measurement)
            mask &= measurement.timestamp_us >= np.uint64(bounds.start_timestamp_us)
            mask &= measurement.timestamp_us <= np.uint64(bounds.end_timestamp_us)
            return bool(np.any(mask))
        if group.measurement_record_names:
            return any(
                bounds.start_timestamp_us
                <= record.timestamp_us
                <= bounds.end_timestamp_us
                for record_name in group.measurement_record_names
                for record in dataset.Records_Get(record_name)
            )
        for channel_id in (
            group.innovation_channel,
            group.nis_channel,
            group.effective_r_channel,
        ):
            series = resolver.Series_Get(channel_id, source.source_id)
            if series is not None and np.any(self._ValidFiniteMask_Get(series)):
                return True
        return False

    def _MeasurementSeries_Get(
        self,
        resolver: ChannelResolver,
        source: AnalysisSource,
        group: MeasurementGroupSpec,
        channel_id: str,
    ) -> TimeSeries | None:
        selected = self._SeriesComponents_Select(
            resolver.Series_Get(channel_id, source.source_id),
            tuple(range(group.dimension)),
            group.component_names,
        )
        if selected is None:
            return None
        return self._MeasurementAttemptMask_Apply(
            resolver,
            source,
            group,
            selected,
        )

    def _MeasurementAttemptMask_Apply(
        self,
        resolver: ChannelResolver,
        source: AnalysisSource,
        group: MeasurementGroupSpec,
        selected: TimeSeries,
    ) -> TimeSeries:
        attempt = resolver.Series_Get(group.attempt_mask_channel, source.source_id)
        if attempt is None or attempt.count == 0 or not group.attempt_mask_bit:
            return selected
        attempt_values = np.asarray(attempt.values, dtype=np.float64).reshape(
            attempt.count,
            -1,
        )[:, 0]
        indices = np.searchsorted(
            attempt.timestamp_us,
            selected.timestamp_us,
            side="right",
        ) - 1
        usable = indices >= 0
        safe_indices = np.clip(indices, 0, max(attempt.count - 1, 0))
        usable &= attempt.valid[safe_indices]
        finite = np.isfinite(attempt_values[safe_indices])
        usable &= finite
        integer_values = np.zeros(indices.shape, dtype=np.int64)
        integer_values[usable] = attempt_values[safe_indices[usable]].astype(
            np.int64
        )
        usable &= (integer_values & group.attempt_mask_bit) != 0
        return TimeSeries(
            timestamp_us=selected.timestamp_us,
            values=selected.values,
            unit=selected.unit,
            quantity=selected.quantity,
            source=selected.source,
            valid=selected.valid & usable,
            columns=selected.columns,
            metadata=selected.metadata,
        )

    def _MeasurementNisSeries_Get(
        self,
        resolver: ChannelResolver,
        source: AnalysisSource,
        group: MeasurementGroupSpec,
    ) -> TimeSeries | None:
        selected = self._SeriesColumn_Select(
            resolver.Series_Get(group.nis_channel, source.source_id),
            0,
            "NIS",
        )
        if selected is None:
            return None
        return self._MeasurementAttemptMask_Apply(
            resolver,
            source,
            group,
            selected,
        )

    def _MeasurementStandardDeviationSeries_Get(
        self,
        resolver: ChannelResolver,
        source: AnalysisSource,
        group: MeasurementGroupSpec,
    ) -> TimeSeries | None:
        channel_id = (
            group.effective_r_channel or group.measurement_uncertainty_channel
        )
        selected = self._MeasurementSeries_Get(
            resolver,
            source,
            group,
            channel_id,
        )
        if selected is None:
            return None
        values = np.asarray(selected.values, dtype=np.float64).copy()
        if group.effective_r_channel:
            values[values < 0.0] = np.nan
            values = np.sqrt(values)
        return TimeSeries(
            timestamp_us=selected.timestamp_us,
            values=values,
            unit=group.unit,
            quantity="measurement_standard_deviation",
            source=selected.source,
            valid=selected.valid & np.all(np.isfinite(values), axis=1),
            columns=group.component_names,
            metadata=selected.metadata,
        )

    @staticmethod
    def _NisThresholds_Get(
        group: MeasurementGroupSpec,
        parameters: Mapping[str, Any],
        language: ExportLanguage,
    ) -> tuple[tuple[float, str, str], ...]:
        translator = Translator(language.value)
        thresholds: list[tuple[float, str, str]] = []
        for reference in group.NisThresholds_Get():
            parameter_id = reference.parameter_id
            label_key = reference.label_key
            style = "-." if reference.hard else "--"
            try:
                value = float(parameters[parameter_id])
            except (KeyError, TypeError, ValueError):
                continue
            if np.isfinite(value):
                thresholds.append(
                    (value, translator.Text_Get(label_key), style)
                )
        return tuple(thresholds)

    def _StandardDiagnosticPlot_Write(
        self,
        dataset: FlightDataset,
        series: TimeSeries | None,
        path: Path,
        title: str,
        ylabel: str,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        empty_message: str,
        thresholds: tuple[tuple[float, str, str], ...] = (),
        end_timestamp_us: int | None = None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        self._Axes_Style(figure, axis, theme)
        plotted = 0
        if series is not None and series.count:
            cropped = _Series_Crop(
                series,
                dataset.start_timestamp_us or 0,
                end_timestamp_us,
            )
            if cropped.count:
                time = self._Time_Get(dataset, cropped)
                values = np.asarray(cropped.values, dtype=np.float64)
                values = values[:, None] if values.ndim == 1 else values
                for index in range(values.shape[1]):
                    component = (
                        cropped.columns[index]
                        if cropped.columns
                        else str(index)
                    )
                    mask = cropped.valid & np.isfinite(values[:, index])
                    if not np.any(mask):
                        continue
                    axis.plot(
                        time,
                        np.where(mask, values[:, index], np.nan),
                        color=_PlotColor_Get(index),
                        linewidth=1.15,
                        label=ComponentLabel_Get(component, language.value),
                    )
                    plotted += 1
        for index, (value, label, style) in enumerate(thresholds):
            axis.axhline(
                value,
                color=_PlotColor_Get(plotted + index),
                linestyle=style,
                linewidth=1.2,
                label=label,
            )
        if plotted == 0:
            axis.text(
                0.5,
                0.5,
                empty_message,
                transform=axis.transAxes,
                horizontalalignment="center",
                verticalalignment="center",
                color=foreground,
                fontsize=11,
                wrap=True,
            )
        display_title = title
        if bool(dataset.metadata.get("synthetic", False)):
            display_title += f" · {_LABELS[language]['synthetic']}"
        axis.set_title(display_title, color=foreground)
        axis.set_xlabel(
            f"{_LABELS[language]['time']} (s)",
            color=foreground,
        )
        axis.set_ylabel(ylabel, color=foreground)
        handles, _ = axis.get_legend_handles_labels()
        if handles:
            axis.legend(
                facecolor=background,
                labelcolor=foreground,
                framealpha=0.82,
            )
        figure.tight_layout()
        self._TimePage_Apply(figure)
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _GnssIntegrityPlot_Write(
        self, dataset, result, kind: str, path: Path,
        language: ExportLanguage, theme: ExportTheme,
        page_start: float, page_end: float, parameters: Mapping[str, object],
        vertical_result=None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt
        background, foreground, _ = self._Plot_Configure(theme)
        label = Translator(language.value).Text_Get
        origin = dataset.start_timestamp_us or int(result.timestamp_us[0])
        time = (result.timestamp_us.astype(np.float64) - origin) * 1e-6
        keep = (time >= page_start) & (time <= page_end)
        if kind == "GNSS_Receiver_Information":
            figure, axes = plt.subplots(2, 1, figsize=(11, 7), dpi=140, sharex=True)
            for axis in axes:
                self._Axes_Style(figure, axis, theme)
            accuracy, satellites = axes
            speed_axis = accuracy.twinx()
            for index, key, color in ((0, "integrity.hacc", "#2b77c2"),
                                      (1, "integrity.vacc", "#1a9d6c")):
                accuracy.plot(time[keep], result.quality[keep, index], color=color,
                              linewidth=1.2, label=label(key))
            speed_axis.plot(time[keep], result.quality[keep, 2], color="#ec8a20",
                            linewidth=1.2, label=label("integrity.sacc"))
            satellites.plot(time[keep], result.quality[keep, 3], color="#9467bd",
                            linewidth=1.2, label=label("integrity.satellites_label"))
            accuracy.set_title(label("integrity.receiver_precision"), color=foreground)
            satellites.set_title(label("integrity.satellites_label"), color=foreground)
            accuracy.set_ylabel("m", color=foreground)
            speed_axis.set_ylabel("m/s", color=foreground)
            speed_axis.tick_params(colors=foreground)
            satellites.set_ylabel(label("integrity.satellites_unit"), color=foreground)
            satellites.set_xlabel(label("timeline.time"), color=foreground)
            accuracy.legend(loc="upper left", facecolor=background, labelcolor=foreground)
            speed_axis.legend(loc="upper right", facecolor=background, labelcolor=foreground)
            satellites.legend(facecolor=background, labelcolor=foreground)
            satellites.set_xlim(page_start, max(page_end, page_start + .001))
        else:
            figure, axis = plt.subplots(figsize=(11, 5), dpi=140)
            self._Axes_Style(figure, axis, theme)
            if kind == "GNSS_Horizontal_Consistency_Error":
                values = result.closure_norm_m[keep].copy()
                values[result.chain_reset[keep]] = np.nan
                axis.plot(time[keep], values, color="#2b77c2", linewidth=1.2,
                          label=label("integrity.horizontal_error"))
                for threshold, key, color in (
                    (parameters.get("gnss_integrity_error_threshold_m", 10.0),
                     "integrity.error_threshold", "#d84a4a"),
                    (parameters.get("gnss_integrity_recovery_threshold_m", 4.0),
                     "integrity.recovery_threshold", "#1a9d6c"),
                ):
                    axis.axhline(float(threshold), color=color, linestyle="--",
                                 linewidth=1, label=label(key))
                for timestamp in time[keep][result.chain_reset[keep]]:
                    axis.axvline(timestamp, color="#9299a5", linewidth=.8)
                events = tuple(record for record in dataset.Records_Get("EVENT")
                               if int(record.payload.get("event_id", -1)) == 0x2E)
                if events:
                    transitions = (((record.timestamp_us - origin) * 1e-6,
                                    (int(record.payload.get("arg0", 0)) >> 8) & 0xFF)
                                   for record in events)
                else:
                    transitions = ((time[index], int(result.state[index]))
                                   for index in range(1, len(result.state))
                                   if result.state[index] != result.state[index - 1])
                for timestamp, state in transitions:
                    if page_start <= timestamp <= page_end and state in (0, 1, 2):
                        axis.axvline(timestamp,
                                     color=("#1a9d6c", "#ec8a20", "#d84a4a")[state],
                                     linewidth=1.2)
                axis.set_title(label("integrity.horizontal_title"), color=foreground)
            elif kind == "GNSS_Vertical_Consistency_Error":
                if vertical_result is None:
                    vertical_result = GnssVerticalConsistency_Build(dataset)
                vertical_time = (vertical_result.timestamp_us.astype(np.float64)
                                 - origin) * 1e-6
                vertical_keep = ((vertical_time >= page_start) &
                                 (vertical_time <= page_end))
                axis.plot(vertical_time[vertical_keep],
                          vertical_result.error_m[vertical_keep],
                          color="#2b77c2", linewidth=1.2,
                          label=label("integrity.vertical_error"))
                axis.axhline(0.0, color="#9299a5", linestyle="--", linewidth=1,
                             label=label("integrity.zero_reference"))
                for timestamp in vertical_time[vertical_keep][
                    vertical_result.chain_reset[vertical_keep]
                ]:
                    axis.axvline(timestamp, color="#9299a5", linewidth=.8)
                axis.set_title(label("integrity.vertical_title"), color=foreground)
                axis.text(.01, .01, label("integrity.vertical_offline_only"),
                          transform=axis.transAxes, color=foreground, fontsize=8)
            else:
                raise ValueError(f"Unknown GNSS integrity plot: {kind}")
            axis.set_xlim(page_start, max(page_end, page_start + .001))
            axis.set_xlabel(label("timeline.time"), color=foreground)
            axis.set_ylabel("m", color=foreground)
            axis.legend(facecolor=background, labelcolor=foreground)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _StandardPlotWorkUnitCount_Get(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        directory: Path,
        suffix: str,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> int:
        work_units = 0

        def attempt_count(*_args: Any, **_kwargs: Any) -> None:
            nonlocal work_units
            work_units += 1

        self._StandardPlots_Write(
            dataset,
            resolver,
            directory,
            suffix,
            language,
            theme,
            attempt_count,
            lambda *_args: None,
        )
        return work_units

    def _StandardPlots_Write(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        directory: Path,
        suffix: str,
        language: ExportLanguage,
        theme: ExportTheme,
        attempt: Callable[..., None],
        skip: Callable[[str, str, str], None],
    ) -> None:
        labels = _LABELS[language]
        active = resolver.store.ActiveSource_Get()
        mission_bounds = FlightDisplayBounds_Get(
            dataset, resolver.MissionReplayBounds_Get(active.source_id)
        )

        def flight_layers(channel_id: str) -> tuple[tuple[TimeSeries, str, str], ...]:
            series = self._Series_Require(resolver.Series_Get(channel_id), channel_id)
            label = (
                labels["recorded"]
                if active.kind == AnalysisSourceKind.RECORDED
                else labels["active"]
            )
            return ((series, label, "-"),)

        standard_flight = (
            (
                "Flight_Velocity_ENU",
                "navigation.velocity_enu",
                "飞行速度（ENU）" if language == ExportLanguage.ZH else "Flight Velocity (ENU)",
                "速度 [m/s]" if language == ExportLanguage.ZH else "Velocity [m/s]",
            ),
            (
                "Flight_Position_ENU",
                "navigation.position_enu",
                "飞行位置（ENU）" if language == ExportLanguage.ZH else "Flight Position (ENU)",
                "位置 [m]" if language == ExportLanguage.ZH else "Position [m]",
            ),
            (
                "Flight_Attitude",
                "attitude.q_nb",
                (
                    "软件姿态四元数（WXYZ，机体 → ENU）"
                    if language == ExportLanguage.ZH
                    else "Software Attitude Quaternion (WXYZ, Body to ENU)"
                ),
                "四元数" if language == ExportLanguage.ZH else "Quaternion",
            ),
        )
        for file_stem, channel_id, title, ylabel in standard_flight:
            path = directory / f"{file_stem}{suffix}.png"
            attempt(
                f"standard_plot:{file_stem}",
                path,
                lambda p=path, c=channel_id, t=title, y=ylabel: self._MultiSeriesPlot_Write(
                    dataset,
                    flight_layers(c),
                    p,
                    t,
                    y,
                    language,
                    theme,
                    end_timestamp_us=mission_bounds.end_timestamp_us,
                ),
                title,
            )

        observed = (
            (
                "Flight_Acceleration_XYZ",
                "imu.corrected.accel_b",
                (
                    "校正后加速度（机体系 XYZ）"
                    if language == ExportLanguage.ZH
                    else "Corrected Acceleration (Body XYZ)"
                ),
                "加速度 [m/s²]" if language == ExportLanguage.ZH else "Acceleration [m/s²]",
            ),
            (
                "Flight_Angular_Rate_XYZ",
                "imu.corrected.gyro_b",
                (
                    "校正后角速度（机体系 XYZ）"
                    if language == ExportLanguage.ZH
                    else "Corrected Angular Rate (Body XYZ)"
                ),
                "角速度 [rad/s]" if language == ExportLanguage.ZH else "Angular Rate [rad/s]",
            ),
        )
        for file_stem, channel_id, title, ylabel in observed:
            if resolver.RecordedSeries_Get(channel_id) is None:
                skip(f"standard_plot:{file_stem}", title, "channel_unavailable:" + channel_id)
                continue
            path = directory / f"{file_stem}{suffix}.png"
            attempt(
                f"standard_plot:{file_stem}",
                path,
                lambda p=path, c=channel_id, t=title, y=ylabel: self._MultiSeriesPlot_Write(
                    dataset,
                    (
                        (
                            self._Series_Require(resolver.RecordedSeries_Get(c), c),
                            labels["recorded"],
                            "-",
                        ),
                    ),
                    p,
                    t,
                    y,
                    language,
                    theme,
                    end_timestamp_us=mission_bounds.end_timestamp_us,
                ),
                title,
            )

        selection = self._EstimatorSelection_Get(resolver)
        if selection is None:
            skip(
                "standard_plot:estimator_visualization",
                (
                    "状态估计标准图"
                    if language == ExportLanguage.ZH
                    else "State Estimation Standard Plots"
                ),
                "estimator_metadata_unavailable",
            )
            return
        source, metadata, visualization = selection
        source_label = self._SourceLabel_Get(source, language)
        algorithm_stem = self._AlgorithmFileStem_Get(metadata)
        source_stem = self._SourceFileStem_Get(source)
        parameters = self._SourceParameters_Get(
            dataset,
            resolver,
            source,
        )
        estimator_bounds = resolver.MissionReplayBounds_Get(source.source_id)

        for group in visualization.state_groups:
            group_label = self._GroupLabel_Get(
                group.group_id,
                group.label_key,
                language,
            )
            group_stem = self._GroupFileStem_Get(
                group.group_id,
                group.file_stem,
            )
            if group.estimate_channel:
                estimate = resolver.Series_Get(group.estimate_channel, source.source_id)
                estimate_title = f"{metadata.display_name} · {source_label} · {group_label}"
                estimate_id = f"standard_plot:estimate:{metadata.plugin_id}:{group.group_id}"
                estimate_path = directory / (
                    f"{algorithm_stem}_{source_stem}_{group_stem}_Estimate{suffix}.png"
                )
                if estimate is None:
                    skip(estimate_id, estimate_title, "state_estimate_channel_unavailable")
                else:
                    attempt(
                        estimate_id, estimate_path,
                        lambda p=estimate_path, s=estimate, t=estimate_title, u=group.unit: (
                            self._StandardDiagnosticPlot_Write(
                                dataset, s, p, t, u, language, theme,
                                empty_message=labels["no_valid_diagnostics"].format(group=t),
                                end_timestamp_us=estimator_bounds.end_timestamp_us,
                            )
                        ),
                        estimate_title,
                    )
            quantity = labels["state_std_quantity"]
            group_quantity = (
                f"{group_label}{quantity}"
                if language == ExportLanguage.ZH
                else f"{group_label} {quantity}"
            )
            title = (
                f"{metadata.display_name} · {source_label} · "
                f"{group_quantity}"
            )
            item_id = (
                f"standard_plot:state_std:{metadata.plugin_id}:"
                f"{source.kind.value}:{group.group_id}"
            )
            path = directory / (
                f"{algorithm_stem}_{source_stem}_{group_stem}_"
                f"Std_1Sigma{suffix}.png"
            )
            series = self._StateStandardDeviationSeries_Get(
                resolver,
                source.source_id,
                group,
            )
            if series is None:
                skip(item_id, title, "state_covariance_channel_unavailable")
                continue
            attempt(
                item_id,
                path,
                lambda p=path, s=series, t=title, u=group.unit, g=group_label: (
                    self._StandardDiagnosticPlot_Write(
                        dataset,
                        s,
                        p,
                        t,
                        (
                            f"标准差（1σ）[{u}]"
                            if language == ExportLanguage.ZH
                            else f"Standard Deviation (1σ) [{u}]"
                        ),
                        language,
                        theme,
                        empty_message=labels["no_valid_diagnostics"].format(
                            group=g
                        ),
                        end_timestamp_us=estimator_bounds.end_timestamp_us,
                    )
                ),
                title,
            )

        for group in visualization.measurement_groups:
            group_label = self._GroupLabel_Get(
                group.measurement_group_id,
                group.label_key,
                language,
            )
            group_stem = self._GroupFileStem_Get(
                group.measurement_group_id,
                group.file_stem,
            )
            configured = self._MeasurementConfigured_Check(dataset, group)
            products = (
                ("innovation", "Innovation", labels["innovation_quantity"]),
                ("nis", "NIS", labels["nis_quantity"]),
                (
                    "measurement_std",
                    "Measurement_Std",
                    labels["measurement_std_quantity"],
                ),
            )
            if not configured:
                for product_id, _, quantity in products:
                    title = (
                        f"{metadata.display_name} · {source_label} · "
                        f"{group_label} · {quantity}"
                    )
                    skip(
                        (
                            f"standard_plot:{product_id}:{metadata.plugin_id}:"
                            f"{source.kind.value}:"
                            f"{group.measurement_group_id}"
                        ),
                        title,
                        "measurement_not_configured",
                    )
                continue

            valid_updates = self._MeasurementHasValidUpdates_Check(
                dataset,
                resolver,
                source,
                group,
            )
            no_update_message = labels["no_valid_updates"].format(
                group=group_label
            )
            diagnostic_message = labels["no_valid_diagnostics"].format(
                group=group_label
            )
            empty_message = (
                diagnostic_message if valid_updates else no_update_message
            )

            innovation_title = (
                f"{metadata.display_name} · {source_label} · "
                f"{group_label} · {labels['innovation_quantity']}"
            )
            innovation_path = directory / (
                f"{algorithm_stem}_{source_stem}_Innovation_"
                f"{group_stem}{suffix}.png"
            )
            innovation_series = (
                self._MeasurementSeries_Get(
                    resolver,
                    source,
                    group,
                    group.innovation_channel,
                )
                if valid_updates
                else None
            )
            attempt(
                (
                    f"standard_plot:innovation:{metadata.plugin_id}:"
                    f"{source.kind.value}:{group.measurement_group_id}"
                ),
                innovation_path,
                lambda p=innovation_path,
                s=innovation_series,
                t=innovation_title,
                e=empty_message,
                u=group.unit: (
                    self._StandardDiagnosticPlot_Write(
                        dataset,
                        s,
                        p,
                        t,
                        (
                            f"新息 [{u}]"
                            if language == ExportLanguage.ZH
                            else f"Innovation [{u}]"
                        ),
                        language,
                        theme,
                        empty_message=e,
                        end_timestamp_us=estimator_bounds.end_timestamp_us,
                    )
                ),
                innovation_title,
            )

            nis_title = (
                f"{metadata.display_name} · {source_label} · "
                f"{group_label} · {labels['nis_quantity']}"
            )
            if group.nis_description_key:
                nis_title += "\n" + Translator(language.value).Text_Get(group.nis_description_key)
            nis_path = directory / (
                f"{algorithm_stem}_{source_stem}_NIS_"
                f"{group_stem}{suffix}.png"
            )
            nis_series = (
                self._MeasurementNisSeries_Get(
                    resolver,
                    source,
                    group,
                )
                if valid_updates
                else None
            )
            thresholds = self._NisThresholds_Get(
                group,
                parameters,
                language,
            )
            attempt(
                (
                    f"standard_plot:nis:{metadata.plugin_id}:"
                    f"{source.kind.value}:{group.measurement_group_id}"
                ),
                nis_path,
                lambda p=nis_path, s=nis_series, t=nis_title, e=empty_message, h=thresholds: (
                    self._StandardDiagnosticPlot_Write(
                        dataset,
                        s,
                        p,
                        t,
                        "NIS [1]",
                        language,
                        theme,
                        empty_message=e,
                        thresholds=h,
                        end_timestamp_us=estimator_bounds.end_timestamp_us,
                    )
                ),
                nis_title,
            )

            standard_deviation_title = (
                f"{metadata.display_name} · {source_label} · "
                f"{group_label} · {labels['measurement_std_quantity']}"
            )
            standard_deviation_path = directory / (
                f"{algorithm_stem}_{source_stem}_Measurement_Std_"
                f"{group_stem}{suffix}.png"
            )
            standard_deviation_series = (
                self._MeasurementStandardDeviationSeries_Get(
                    resolver,
                    source,
                    group,
                )
                if valid_updates
                else None
            )
            attempt(
                (
                    f"standard_plot:measurement_std:{metadata.plugin_id}:"
                    f"{source.kind.value}:{group.measurement_group_id}"
                ),
                standard_deviation_path,
                lambda p=standard_deviation_path,
                s=standard_deviation_series,
                t=standard_deviation_title,
                e=empty_message,
                u=group.unit: (
                    self._StandardDiagnosticPlot_Write(
                        dataset,
                        s,
                        p,
                        t,
                        (
                            f"量测标准差 sqrt(R) [{u}]"
                            if language == ExportLanguage.ZH
                            else (
                                "Measurement Standard Deviation "
                                f"sqrt(R) [{u}]"
                            )
                        ),
                        language,
                        theme,
                        empty_message=e,
                        end_timestamp_us=estimator_bounds.end_timestamp_us,
                    )
                ),
                standard_deviation_title,
            )

        update_title = (
            f"{metadata.display_name} · {source_label} · "
            f"{labels['measurement_update']}"
        )
        update_path = directory / (
            f"{algorithm_stem}_{source_stem}_Measurement_Update"
            f"{suffix}.png"
        )
        attempt(
            (
                f"standard_plot:measurement_update:{metadata.plugin_id}:"
                f"{source.kind.value}"
            ),
            update_path,
            lambda: self._MeasurementUpdatePlot_Write(
                dataset,
                resolver,
                source,
                visualization.measurement_groups,
                update_path,
                update_title,
                language,
                theme,
                end_timestamp_us=estimator_bounds.end_timestamp_us,
            ),
            update_title,
        )

    def _MeasurementUpdatePlot_Write(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        source: AnalysisSource,
        groups: tuple[MeasurementGroupSpec, ...],
        path: Path,
        title: str,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        end_timestamp_us: int | None = None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        result_layers: list[tuple[MeasurementGroupSpec, TimeSeries]] = []
        scale_layers: list[tuple[MeasurementGroupSpec, TimeSeries]] = []
        for group in groups:
            result = self._SeriesColumn_Select(
                resolver.Series_Get(
                    group.update_result_channel,
                    source.source_id,
                ),
                group.update_result_index,
                group.measurement_group_id,
            )
            if result is not None:
                result_layers.append(
                    (
                        group,
                        self._MeasurementAttemptMask_Apply(
                            resolver,
                            source,
                            group,
                            result,
                        ),
                    )
                )
            scale = self._SeriesColumn_Select(
                resolver.Series_Get(
                    group.r_scale_channel,
                    source.source_id,
                ),
                group.r_scale_index,
                group.measurement_group_id,
            )
            if scale is not None:
                scale_layers.append(
                    (
                        group,
                        self._MeasurementAttemptMask_Apply(
                            resolver,
                            source,
                            group,
                            scale,
                        ),
                    )
                )
        rows = 2 if scale_layers else 1
        figure, axes = plt.subplots(rows, 1, figsize=(10, 6 if rows == 2 else 4.5), dpi=140)
        axes_array = np.atleast_1d(axes)
        self._Axes_Style(figure, axes_array[0], theme)
        result_count = 0
        for index, (group, result) in enumerate(result_layers):
            cropped = _Series_Crop(
                result,
                dataset.start_timestamp_us or 0,
                end_timestamp_us,
            )
            if cropped.count == 0:
                continue
            values = np.asarray(cropped.values, dtype=np.float64).reshape(
                cropped.count,
                -1,
            )[:, 0]
            mask = cropped.valid & np.isfinite(values)
            if not np.any(mask):
                continue
            time = self._Time_Get(dataset, cropped)
            axes_array[0].step(
                time[mask],
                values[mask],
                where="post",
                color=_PlotColor_Get(index),
                label=self._GroupLabel_Get(
                    group.measurement_group_id,
                    group.label_key,
                    language,
                ),
            )
            result_count += 1
        result_labels = (
            ("接受", "软降权", "NIS 拒绝", "无效", "数值错误", "未尝试")
            if language == ExportLanguage.ZH
            else (
                "Accepted",
                "Soft Weighted",
                "NIS Rejected",
                "Invalid",
                "Numeric Error",
                "Not Attempted",
            )
        )
        axes_array[0].set_yticks(range(6), result_labels)
        display_title = title
        if bool(dataset.metadata.get("synthetic", False)):
            display_title += f" · {_LABELS[language]['synthetic']}"
        axes_array[0].set_title(display_title, color=foreground)
        axes_array[0].set_ylabel(
            "更新结果" if language == ExportLanguage.ZH else "Update Result",
            color=foreground,
        )
        if result_count:
            axes_array[0].legend(
                facecolor=background,
                labelcolor=foreground,
                framealpha=0.82,
            )
        else:
            axes_array[0].text(
                0.5,
                0.5,
                (
                    "未记录有效的量测更新诊断"
                    if language == ExportLanguage.ZH
                    else "No valid measurement update diagnostics were recorded."
                ),
                transform=axes_array[0].transAxes,
                horizontalalignment="center",
                verticalalignment="center",
                color=foreground,
            )
        if rows == 2:
            self._Axes_Style(figure, axes_array[1], theme)
            scale_count = 0
            for index, (group, scale) in enumerate(scale_layers):
                cropped_scale = _Series_Crop(
                    scale,
                    dataset.start_timestamp_us or 0,
                    end_timestamp_us,
                )
                if cropped_scale.count == 0:
                    continue
                scale_values = np.asarray(
                    cropped_scale.values,
                    dtype=np.float64,
                ).reshape(cropped_scale.count, -1)[:, 0]
                mask = cropped_scale.valid & np.isfinite(scale_values)
                if not np.any(mask):
                    continue
                scale_time = self._Time_Get(dataset, cropped_scale)
                axes_array[1].plot(
                    scale_time[mask],
                    scale_values[mask],
                    color=_PlotColor_Get(index),
                    label=self._GroupLabel_Get(
                        group.measurement_group_id,
                        group.label_key,
                        language,
                    ),
                )
                scale_count += 1
            axes_array[1].set_ylabel("R 缩放" if language == ExportLanguage.ZH else "R Scale")
            if scale_count:
                axes_array[1].legend(
                    facecolor=background,
                    labelcolor=foreground,
                    framealpha=0.82,
                )
        axes_array[-1].set_xlabel(f"{_LABELS[language]['time']} (s)", color=foreground)
        figure.tight_layout()
        self._TimePage_Apply(figure)
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _Position_At(position: TimeSeries, timestamp_us: int) -> np.ndarray | None:
        return TrajectoryPosition_At(position, timestamp_us)

    @staticmethod
    def _Position_NearEvent(
        position: TimeSeries,
        timestamp_us: int,
    ) -> np.ndarray | None:
        return TrajectoryPosition_NearEvent(position, timestamp_us)

    @staticmethod
    def _TrajectoryOrigin_Get(
        position: TimeSeries,
        start_timestamp_us: int,
    ) -> np.ndarray:
        return TrajectoryOrigin_Get(position, start_timestamp_us)

    def _HorizontalTrajectory_Write(self, dataset, position, path, language, theme,
                                    mission_bounds, page_range) -> None:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        start = mission_bounds.start_timestamp_us
        end = mission_bounds.end_timestamp_us
        deploy = _Event_Timestamp(dataset, 0x29)
        origin = TrajectoryOrigin_Get(position, start) if position is not None else np.zeros(3)
        trajectory = HorizontalTrajectory_Build(
            position.time_s if position is not None else [],
            position.values if position is not None else [],
            valid=position.valid if position is not None else None, origin_enu=origin,
            mission_range=(start * 1e-6, end * 1e-6),
            time_range=(start * 1e-6 + page_range[0], start * 1e-6 + page_range[1]),
            deploy_time_s=deploy * 1e-6 if deploy is not None else None,
            breaks_s=tuple(t * 1e-6 for t in
                           position.metadata.get("discontinuity_timestamps_us", ()))
                     if position is not None else (),
        )
        figure = Figure(figsize=(8, 6))
        FigureCanvasAgg(figure)
        translator = Translator(language.value)
        labels = {key: translator.Text_Get("horizontal." + key) for key in LABEL_IDS}
        HorizontalTrajectory_Draw(figure, trajectory, labels, theme=theme.value)
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=160, facecolor=figure.get_facecolor())

    @staticmethod
    def _Axis3d_Equal(axis: Any, values: np.ndarray) -> None:
        if values.size == 0:
            return
        minimum = np.nanmin(values, axis=0)
        maximum = np.nanmax(values, axis=0)
        center = (minimum + maximum) * 0.5
        radius = max(float(np.nanmax(maximum - minimum)) * 0.55, 1.0)
        axis.set_xlim(center[0] - radius, center[0] + radius)
        axis.set_ylim(center[1] - radius, center[1] + radius)
        axis.set_zlim(center[2] - radius, center[2] + radius)
        with suppress(AttributeError):
            axis.set_box_aspect((1.0, 1.0, 1.0))

    def _Axis3d_ThemeApply(self, axis: Any, theme: ExportTheme) -> None:
        background, foreground, grid = self._Plot_Configure(theme)
        axis.set_facecolor(background)
        axis.tick_params(colors=foreground)
        axis.grid(True)
        for coordinate_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
            coordinate_axis.pane.set_facecolor(background)
            coordinate_axis.pane.set_edgecolor(grid)
            coordinate_axis._axinfo["grid"]["color"] = grid
            coordinate_axis._axinfo["grid"]["linewidth"] = 0.55
            coordinate_axis._axinfo["grid"]["linestyle"] = ":"

    @staticmethod
    def _TrajectoryGroundPlaneBounds_Get(
        values: np.ndarray,
    ) -> tuple[float, float, float, float]:
        points = np.asarray(values, dtype=np.float64).reshape(-1, 3)
        finite = points[np.all(np.isfinite(points), axis=1)]
        if finite.size == 0:
            return (-1.0, 1.0, -1.0, 1.0)
        x_min = float(np.min(finite[:, 0]))
        x_max = float(np.max(finite[:, 0]))
        y_min = float(np.min(finite[:, 1]))
        y_max = float(np.max(finite[:, 1]))
        horizontal_span = max(x_max - x_min, y_max - y_min, 1.0)
        padding = max(horizontal_span * 0.05, 0.5)
        if x_max - x_min < 1.0e-9:
            x_min -= horizontal_span * 0.5
            x_max += horizontal_span * 0.5
        if y_max - y_min < 1.0e-9:
            y_min -= horizontal_span * 0.5
            y_max += horizontal_span * 0.5
        return (
            x_min - padding,
            x_max + padding,
            y_min - padding,
            y_max + padding,
        )

    @staticmethod
    def _TrajectoryGroundPlane_Add(
        axis: Any,
        bounds: tuple[float, float, float, float],
        theme: ExportTheme,
    ) -> Any:
        x_min, x_max, y_min, y_max = bounds
        x_grid, y_grid = np.meshgrid(
            np.asarray((x_min, x_max), dtype=np.float64),
            np.asarray((y_min, y_max), dtype=np.float64),
        )
        if theme == ExportTheme.DARK:
            color = "#4F86A6"
            edge_color = "#79B8D8"
        else:
            color = "#75B5D8"
            edge_color = "#3F86AE"
        plane = axis.plot_surface(
            x_grid,
            y_grid,
            np.zeros_like(x_grid),
            color=color,
            edgecolor=edge_color,
            alpha=0.30,
            linewidth=0.65,
            antialiased=True,
            shade=False,
            label="_nolegend_",
        )
        plane.set_gid("trajectory_ground_plane")
        return plane

    def _Trajectory_AxisDraw(
        self,
        axis: Any,
        dataset: FlightDataset,
        position: TimeSeries,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        current_timestamp_us: int | None = None,
        mission_bounds: MissionReplayBounds | None = None,
        trajectory_bounds: TrajectoryBounds | None = None,
    ) -> None:
        background, foreground, _ = self._Plot_Configure(theme)
        source_end = int(position.timestamp_us[-1])
        resolved_mission = mission_bounds or MissionReplayBounds_Get(
            dataset,
            source_end_timestamp_us=source_end,
        )
        resolved_bounds = trajectory_bounds or TrajectoryBounds_Calculate(
            position,
            resolved_mission,
        )
        start = resolved_mission.start_timestamp_us
        display_timestamp = min(
            (
                resolved_mission.end_timestamp_us
                if current_timestamp_us is None
                else current_timestamp_us
            ),
            resolved_mission.end_timestamp_us,
        )
        origin = np.asarray(resolved_bounds.origin_enu, dtype=np.float64)
        cropped = _Series_Crop(position, start, display_timestamp)
        cropped_values = np.asarray(cropped.values, dtype=np.float64)
        finite_valid = cropped.valid & np.all(np.isfinite(cropped_values), axis=1)
        cropped = TimeSeries(
            timestamp_us=cropped.timestamp_us[finite_valid],
            values=cropped_values[finite_valid],
            unit=cropped.unit,
            quantity=cropped.quantity,
            source=cropped.source,
            valid=np.ones(int(np.count_nonzero(finite_valid)), dtype=np.bool_),
            columns=cropped.columns,
            metadata=cropped.metadata,
        )
        if cropped.count == 0:
            raise ValueError("trajectory_has_no_post_start_samples")
        values = np.asarray(cropped.values, dtype=np.float64) - origin
        full_values = np.asarray(
            (resolved_bounds.min_enu, resolved_bounds.max_enu),
            dtype=np.float64,
        )
        ground_bounds = self._TrajectoryGroundPlaneBounds_Get(full_values)
        self._TrajectoryGroundPlane_Add(axis, ground_bounds, theme)
        deploy_size, _, landing_size = TrajectoryMarkerWorldSizesFromExtent_Get(
            resolved_bounds.max_span
        )
        deploy = _Event_Timestamp(dataset, _EVENT_DEPLOY)
        landing = _Event_Timestamp(dataset, _EVENT_LANDING)
        segments = TrajectoryPhaseSegments_Build(
            position, (() if deploy is None else (deploy,)),
            start_timestamp_us=start, end_timestamp_us=display_timestamp,
        )
        pre, post = (TrajectoryPhaseValues_Get(segments, phase, origin=origin)
                     for phase in (0, 1))
        labels = _LABELS[language]
        if pre.size:
            axis.plot(
                pre[:, 0],
                pre[:, 1],
                pre[:, 2],
                color=TRAJECTORY_PRE_DEPLOY_COLOR,
                linewidth=1.7,
                label=labels["pre_deploy"],
            )
        if post.size:
            axis.plot(
                post[:, 0],
                post[:, 1],
                post[:, 2],
                color=TRAJECTORY_POST_DEPLOY_COLOR,
                linewidth=1.7,
                label=labels["post_deploy"],
            )
        if deploy is not None and deploy <= int(cropped.timestamp_us[-1]):
            point = self._Position_At(position, deploy)
            if point is not None:
                point = point - origin
                deploy_vertices, deploy_faces = TrajectoryEventMesh_Get(
                    point,
                    deploy_size,
                )
                from mpl_toolkits.mplot3d.art3d import Poly3DCollection

                deploy_marker = Poly3DCollection(
                    [deploy_vertices[face] for face in deploy_faces],
                    facecolors=TRAJECTORY_DEPLOY_COLOR,
                    edgecolors=TRAJECTORY_DEPLOY_COLOR,
                    linewidths=0.25,
                    alpha=1.0,
                    label=labels["deploy"],
                )
                axis.add_collection3d(deploy_marker)
        landing_reached = landing is not None and landing <= display_timestamp
        if landing is not None and landing_reached:
            point = self._Position_NearEvent(position, landing)
            if point is not None:
                point = point - origin
                landing_vertices, landing_faces = TrajectoryEventMesh_Get(
                    point,
                    landing_size,
                )
                from mpl_toolkits.mplot3d.art3d import Poly3DCollection

                landing_marker = Poly3DCollection(
                    [landing_vertices[face] for face in landing_faces],
                    facecolors=TRAJECTORY_LANDING_COLOR,
                    edgecolors=TRAJECTORY_LANDING_COLOR,
                    linewidths=0.25,
                    alpha=1.0,
                    label=labels["landing"],
                )
                axis.add_collection3d(landing_marker)
        if not landing_reached:
            axis.scatter(
                *values[-1],
                color=TrajectoryPhaseColor_Get(
                    int(cropped.timestamp_us[-1]),
                    deploy,
                ),
                s=38,
                marker="o",
                label=labels["current"],
            )
        self._Axis3d_ThemeApply(axis, theme)
        axis.set_xlabel("E (m)", color=foreground)
        axis.set_ylabel("N (m)", color=foreground)
        axis.set_zlabel("U (m)", color=foreground)
        axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.78)
        self._Axis3d_Equal(axis, full_values)
        axis.view_init(
            elev=_TRAJECTORY_VIEW_ELEVATION,
            azim=_TRAJECTORY_VIEW_AZIMUTH,
        )

    def _Trajectory_Write(
        self,
        dataset: FlightDataset,
        position: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        mission_bounds: MissionReplayBounds | None = None,
        trajectory_bounds: TrajectoryBounds | None = None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        figure = plt.figure(figsize=(8, 7), dpi=150)
        figure.patch.set_facecolor(background)
        axis = figure.add_subplot(111, projection="3d")
        self._Trajectory_AxisDraw(
            axis,
            dataset,
            position,
            language,
            theme,
            mission_bounds=mission_bounds,
            trajectory_bounds=trajectory_bounds,
        )
        title = _LABELS[language]["trajectory"]
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" · {_LABELS[language]['synthetic']}"
        axis.set_title(title, color=foreground)
        figure.tight_layout()
        self._TimePage_Apply(figure)
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _NearestIndex(timestamps: np.ndarray, timestamp_us: int) -> int:
        if timestamps.size == 0:
            return 0
        upper = int(np.searchsorted(timestamps, np.uint64(timestamp_us), side="left"))
        if upper <= 0:
            return 0
        if upper >= timestamps.size:
            return int(timestamps.size - 1)
        before = int(timestamps[upper - 1])
        after = int(timestamps[upper])
        return upper - 1 if timestamp_us - before <= after - timestamp_us else upper

    @staticmethod
    def _ReplayTimeRange_Get(
        attitude: TimeSeries,
        position: TimeSeries,
        start_timestamp_us: int,
        end_timestamp_us: int | None = None,
    ) -> tuple[int, int] | None:
        start_floor = max(start_timestamp_us, 0)
        attitude_values = np.asarray(attitude.values, dtype=np.float64)
        position_values = np.asarray(position.values, dtype=np.float64)
        if attitude_values.ndim != 2 or attitude_values.shape[1] != 4:
            return None
        if position_values.ndim != 2 or position_values.shape[1] != 3:
            return None
        attitude_valid = attitude.valid & np.all(np.isfinite(attitude_values), axis=1)
        position_valid = position.valid & np.all(np.isfinite(position_values), axis=1)
        attitude_times = attitude.timestamp_us[
            attitude_valid & (attitude.timestamp_us >= np.uint64(start_floor))
        ]
        position_times = position.timestamp_us[
            position_valid & (position.timestamp_us >= np.uint64(start_floor))
        ]
        if attitude_times.size == 0 or position_times.size == 0:
            return None
        available_start = max(int(attitude_times[0]), int(position_times[0]))
        start = (
            start_floor
            if available_start - start_floor <= 100_000
            else available_start
        )
        attitude_end = int(attitude_times[-1])
        position_end = int(position_times[-1])
        end = min(attitude_end, position_end)
        if end_timestamp_us is not None:
            requested_end = max(int(end_timestamp_us), 0)
            if requested_end <= end:
                end = requested_end
            elif (
                max(requested_end - attitude_end, 0) <= 100_000
                and max(requested_end - position_end, 0) <= 100_000
            ):
                # A Landing event can legitimately trail the final discrete
                # solution by a fraction of a sample interval.
                end = requested_end
        if end < start:
            return None
        return start, end

    @classmethod
    def _ReplayFrameTimestamps_Get(
        cls,
        attitude: TimeSeries,
        position: TimeSeries,
        start_timestamp_us: int,
        frames_per_second: int = _REPLAY_FRAMES_PER_SECOND,
        end_timestamp_us: int | None = None,
        key_event_timestamps: tuple[int, ...] = (),
    ) -> np.ndarray:
        if frames_per_second <= 0:
            raise ValueError("frames_per_second_must_be_positive")
        time_range = cls._ReplayTimeRange_Get(
            attitude,
            position,
            start_timestamp_us,
            end_timestamp_us,
        )
        if time_range is None:
            return np.asarray([], dtype=np.uint64)
        start, end = time_range
        duration_us = end - start
        main_frame_count = max(
            1,
            int(np.ceil(min(duration_us, 30_000_000) * frames_per_second / 1_000_000.0)),
        )
        targets = np.linspace(
            start,
            end,
            main_frame_count,
            endpoint=False,
        ).round().astype(np.uint64)
        return targets

    @staticmethod
    def _RocketVertices_Rotate(quaternion: np.ndarray) -> np.ndarray:
        return np.asarray(
            [
                Quaternion_RotateVector(quaternion, vertex)
                for vertex in _ROCKET_BASE_VERTICES
            ],
            dtype=np.float64,
        )

    @classmethod
    def _RocketPolygons_Get(cls, quaternion: np.ndarray) -> list[np.ndarray]:
        rotated_vertices = cls._RocketVertices_Rotate(quaternion)
        return [rotated_vertices[face] for face in _ROCKET_FACES]

    def _Attitude_AxisDraw(
        self,
        axis: Any,
        quaternion: np.ndarray,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> Any:
        background, foreground, _ = self._Plot_Configure(theme)
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        face_colors = RocketFaceColors_Get(theme.value)
        rocket = Poly3DCollection(
            self._RocketPolygons_Get(quaternion),
            facecolors=face_colors,
            edgecolors=foreground,
            linewidths=0.6,
            alpha=1.0,
        )
        axis.add_collection3d(rocket)
        self._Axis3d_ThemeApply(axis, theme)
        axis.set_xlim(-_ATTITUDE_AXIS_LIMIT, _ATTITUDE_AXIS_LIMIT)
        axis.set_ylim(-_ATTITUDE_AXIS_LIMIT, _ATTITUDE_AXIS_LIMIT)
        axis.set_zlim(-_ATTITUDE_AXIS_LIMIT, _ATTITUDE_AXIS_LIMIT)
        axis.set_box_aspect((1.0, 1.0, 1.0))
        axis.view_init(
            elev=_ATTITUDE_VIEW_ELEVATION,
            azim=_ATTITUDE_VIEW_AZIMUTH,
        )
        axis.set_xlabel("X", color=foreground)
        axis.set_ylabel("Y", color=foreground)
        axis.set_zlabel("Z", color=foreground)
        axis.set_title(_LABELS[language]["attitude"], color=foreground)
        return rocket

    @staticmethod
    def _ReplayEventFrameIndices_Get(
        frame_timestamps: np.ndarray,
        event_timestamps: Mapping[str, int | None],
    ) -> dict[str, int]:
        if frame_timestamps.size == 0:
            return {}
        first = int(frame_timestamps[0])
        last = int(frame_timestamps[-1])
        indices: dict[str, int] = {}
        for name, timestamp_us in event_timestamps.items():
            if timestamp_us is None or timestamp_us < first or timestamp_us > last:
                continue
            index = int(
                np.searchsorted(
                    frame_timestamps,
                    np.uint64(timestamp_us),
                    side="left",
                )
            )
            indices[name] = min(index, int(frame_timestamps.size - 1))
        return indices

    def _ReplayFrameSamples_Precompute(
        self,
        attitude: TimeSeries,
        trajectory_timestamps: np.ndarray,
        trajectory_values: np.ndarray,
        frame_timestamps: np.ndarray,
        deploy_timestamp_us: int | None,
        landing_timestamp_us: int | None,
        event_frame_indices: Mapping[str, int],
        phase_segments: tuple[TrajectoryPhaseSegment, ...] | None = None,
    ) -> tuple[_ReplayFrameSample, ...]:
        if phase_segments is None:
            phase_segments = TrajectoryPhaseSegments_Build(
                TimeSeries(trajectory_timestamps, trajectory_values, "m", "position", "display",
                           np.ones(trajectory_timestamps.size, dtype=np.bool_)),
                (() if deploy_timestamp_us is None else (deploy_timestamp_us,)),
            )
        deploy_frame = event_frame_indices.get("deploy")
        landing_frame = event_frame_indices.get("landing")
        samples: list[_ReplayFrameSample] = []
        for frame_index, raw_timestamp in enumerate(frame_timestamps):
            timestamp_us = int(raw_timestamp)
            attitude_index = self._NearestIndex(
                attitude.timestamp_us,
                timestamp_us,
            )
            trajectory_end = int(
                np.searchsorted(
                    trajectory_timestamps,
                    raw_timestamp,
                    side="right",
                )
            )
            trajectory_end = max(1, min(trajectory_end, trajectory_timestamps.size))
            samples.append(
                _ReplayFrameSample(
                    timestamp_us=timestamp_us,
                    quaternion=np.asarray(
                        attitude.values[attitude_index],
                        dtype=np.float64,
                    ).copy(),
                    pre_deploy_values=TrajectoryPhaseValues_Get(
                        phase_segments, 0, timestamp_us=timestamp_us),
                    post_deploy_values=TrajectoryPhaseValues_Get(
                        phase_segments, 1, timestamp_us=timestamp_us),
                    current_position=np.asarray(
                        trajectory_values[trajectory_end - 1],
                        dtype=np.float64,
                    ).copy(),
                    current_color=TrajectoryPhaseColor_Get(
                        timestamp_us,
                        deploy_timestamp_us,
                    ),
                    deploy_visible=(
                        deploy_frame is not None and frame_index >= deploy_frame
                    ),
                    landing_visible=(
                        landing_timestamp_us is not None
                        and landing_frame is not None
                        and frame_index >= landing_frame
                    ),
                )
            )
        return tuple(samples)

    def _ReplayTrajectoryArtists_Create(
        self,
        axis: Any,
        language: ExportLanguage,
        theme: ExportTheme,
        full_values: np.ndarray,
        ground_bounds: tuple[float, float, float, float],
        deploy_mesh: tuple[np.ndarray, np.ndarray] | None,
        landing_mesh: tuple[np.ndarray, np.ndarray] | None,
    ) -> _ReplayTrajectoryArtists:
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        background, foreground, _ = self._Plot_Configure(theme)
        labels = _LABELS[language]
        self._TrajectoryGroundPlane_Add(axis, ground_bounds, theme)
        pre_deploy_line = axis.plot(
            [],
            [],
            [],
            color=TRAJECTORY_PRE_DEPLOY_COLOR,
            linewidth=1.7,
            label=labels["pre_deploy"],
        )[0]
        post_deploy_line = axis.plot(
            [],
            [],
            [],
            color=TRAJECTORY_POST_DEPLOY_COLOR,
            linewidth=1.7,
            label=labels["post_deploy"],
        )[0]
        current_marker = axis.plot(
            [],
            [],
            [],
            color=TRAJECTORY_PRE_DEPLOY_COLOR,
            linestyle="None",
            marker="o",
            markersize=6.2,
            label="_nolegend_",
        )[0]

        def marker_create(
            mesh: tuple[np.ndarray, np.ndarray] | None,
            color: str,
            label: str,
        ) -> Any | None:
            if mesh is None:
                return None
            vertices, faces = mesh
            marker = Poly3DCollection(
                [vertices[face] for face in faces],
                facecolors=color,
                edgecolors=color,
                linewidths=0.25,
                alpha=1.0,
                label=label,
            )
            marker.set_visible(False)
            axis.add_collection3d(marker)
            return marker

        deploy_marker = marker_create(
            deploy_mesh,
            TRAJECTORY_DEPLOY_COLOR,
            labels["deploy"],
        )
        landing_marker = marker_create(
            landing_mesh,
            TRAJECTORY_LANDING_COLOR,
            labels["landing"],
        )
        self._Axis3d_ThemeApply(axis, theme)
        axis.set_xlabel("E (m)", color=foreground)
        axis.set_ylabel("N (m)", color=foreground)
        axis.set_zlabel("U (m)", color=foreground)
        axis.set_title(labels["trajectory_panel"], color=foreground)
        self._Axis3d_Equal(axis, full_values)
        axis.view_init(
            elev=_TRAJECTORY_VIEW_ELEVATION,
            azim=_TRAJECTORY_VIEW_AZIMUTH,
        )
        axis.legend(
            facecolor=background,
            labelcolor=foreground,
            framealpha=0.78,
            loc="best",
        )
        return _ReplayTrajectoryArtists(
            pre_deploy_line=pre_deploy_line,
            post_deploy_line=post_deploy_line,
            current_marker=current_marker,
            deploy_marker=deploy_marker,
            landing_marker=landing_marker,
        )

    @staticmethod
    def _ReplayTrajectoryArtists_Update(
        artists: _ReplayTrajectoryArtists,
        sample: _ReplayFrameSample,
    ) -> None:
        pre_deploy = sample.pre_deploy_values
        post_deploy = sample.post_deploy_values

        def line_update(line: Any, values: np.ndarray) -> None:
            if values.size:
                line.set_data_3d(values[:, 0], values[:, 1], values[:, 2])
            else:
                line.set_data_3d([], [], [])

        line_update(artists.pre_deploy_line, pre_deploy)
        line_update(artists.post_deploy_line, post_deploy)
        current = sample.current_position
        artists.current_marker.set_data_3d(
            [current[0]],
            [current[1]],
            [current[2]],
        )
        artists.current_marker.set_color(sample.current_color)
        artists.current_marker.set_visible(not sample.landing_visible)
        if artists.deploy_marker is not None:
            artists.deploy_marker.set_visible(sample.deploy_visible)
        if artists.landing_marker is not None:
            artists.landing_marker.set_visible(sample.landing_visible)

    @staticmethod
    def _FrameDurations_Distribute(
        total_duration_ms: float,
        frame_count: int,
    ) -> list[int]:
        if frame_count <= 0:
            return []
        centiseconds = max(
            frame_count,
            int(round(max(total_duration_ms, 0.0) / 10.0)),
        )
        boundaries = np.rint(
            np.linspace(0, centiseconds, frame_count + 1)
        ).astype(np.int64)
        return (np.diff(boundaries) * 10).astype(int).tolist()

    @classmethod
    def _ReplayFrameDurations_Get(
        cls,
        main_frame_count: int,
        mission_duration_us: int,
        hold_frame_count: int = _REPLAY_FINAL_HOLD_FRAME_COUNT,
    ) -> list[int]:
        main = cls._FrameDurations_Distribute(
            min(max(mission_duration_us, 0), 30_000_000) * 1.0e-3,
            main_frame_count,
        )
        hold = cls._FrameDurations_Distribute(
            _REPLAY_FINAL_HOLD_DURATION_MS,
            hold_frame_count,
        )
        return [*main, *hold]

    @staticmethod
    def _GifFrameSequenceTag_Apply(image: Any, frame_index: int) -> None:
        # GIF encoders merge byte-identical adjacent frames. Two palette entries
        # with the same corner color keep copied hold frames visually identical
        # while retaining every physical frame and its timing metadata.
        palette = list(image.getpalette() or [])
        corner_index = int(image.getpixel((0, 0)))
        color_start = corner_index * 3
        corner_color = palette[color_start : color_start + 3]
        if len(corner_color) != 3:
            corner_color = list(image.convert("RGB").getpixel((0, 0)))
        palette.extend([0] * (768 - len(palette)))
        for tag_index in (254, 255):
            start = tag_index * 3
            palette[start : start + 3] = corner_color
        image.putpalette(palette)
        image.putpixel((0, 0), 254 + frame_index % 2)

    def _FlightReplayGif_Write(
        self,
        dataset: FlightDataset,
        attitude: TimeSeries,
        position: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
        progress: _ExportProgressTracker,
        *,
        mission_bounds: MissionReplayBounds | None = None,
        trajectory_bounds: TrajectoryBounds | None = None,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt
        from PIL import Image

        attitude_values = np.asarray(attitude.values, dtype=np.float64)
        position_values = np.asarray(position.values, dtype=np.float64)
        geometry_position = position
        if attitude_values.ndim != 2 or attitude_values.shape[1] != 4:
            raise ValueError("attitude_channel_must_be_wxyz")
        if position_values.ndim != 2 or position_values.shape[1] != 3:
            raise ValueError("position_channel_must_be_enu")
        attitude_valid = attitude.valid & np.all(np.isfinite(attitude_values), axis=1)
        position_valid = position.valid & np.all(np.isfinite(position_values), axis=1)
        attitude = TimeSeries(
            timestamp_us=attitude.timestamp_us[attitude_valid],
            values=attitude_values[attitude_valid],
            unit=attitude.unit,
            quantity=attitude.quantity,
            source=attitude.source,
            valid=np.ones(int(np.count_nonzero(attitude_valid)), dtype=np.bool_),
            columns=attitude.columns,
            metadata=attitude.metadata,
        )
        position = TimeSeries(
            timestamp_us=position.timestamp_us[position_valid],
            values=position_values[position_valid],
            unit=position.unit,
            quantity=position.quantity,
            source=position.source,
            valid=np.ones(int(np.count_nonzero(position_valid)), dtype=np.bool_),
            columns=position.columns,
            metadata=position.metadata,
        )
        if attitude.count == 0 or position.count == 0:
            raise ValueError("no_valid_attitude_or_position_samples")
        source_end = max(
            int(attitude.timestamp_us[-1]),
            int(position.timestamp_us[-1]),
        )
        resolved_mission = mission_bounds or MissionReplayBounds_Get(
            dataset,
            source_end_timestamp_us=source_end,
        )
        resolved_bounds = trajectory_bounds or TrajectoryBounds_Calculate(
            geometry_position,
            resolved_mission,
        )
        start = resolved_mission.start_timestamp_us
        deploy = _Event_Timestamp(dataset, _EVENT_DEPLOY)
        if deploy is not None and not (
            start <= deploy <= resolved_mission.end_timestamp_us
        ):
            deploy = None
        landing = (
            resolved_mission.end_timestamp_us
            if resolved_mission.end_reason == MissionReplayEndReason.LANDING
            else None
        )
        key_event_timestamps = tuple(
            timestamp
            for timestamp in (start, deploy, landing)
            if timestamp is not None
        )
        frame_timestamps = self._ReplayFrameTimestamps_Get(
            attitude,
            position,
            start,
            frames_per_second=_REPLAY_FRAMES_PER_SECOND,
            end_timestamp_us=resolved_mission.end_timestamp_us,
            key_event_timestamps=key_event_timestamps,
        )
        if frame_timestamps.size == 0:
            raise ValueError("no_common_post_start_attitude_and_position")
        time_range = self._ReplayTimeRange_Get(
            attitude,
            position,
            start,
            resolved_mission.end_timestamp_us,
        )
        if time_range is None:
            raise ValueError("no_common_post_start_attitude_and_position")
        effective_start, terminal_timestamp = time_range
        render_timestamps = np.append(
            frame_timestamps,
            np.uint64(terminal_timestamp),
        )
        trajectory_mask = (
            (position.timestamp_us >= np.uint64(max(start, 0)))
            & (
                position.timestamp_us
                <= np.uint64(max(resolved_mission.end_timestamp_us, 0))
            )
        )
        trajectory_timestamps = position.timestamp_us[trajectory_mask]
        if trajectory_timestamps.size == 0:
            raise ValueError("trajectory_has_no_mission_samples")
        origin = np.asarray(resolved_bounds.origin_enu, dtype=np.float64)
        trajectory_values = (
            np.asarray(position.values[trajectory_mask], dtype=np.float64) - origin
        )
        event_frame_indices = self._ReplayEventFrameIndices_Get(
            render_timestamps,
            {
                "start": start,
                "deploy": deploy,
                "landing": landing,
            },
        )
        frame_samples = self._ReplayFrameSamples_Precompute(
            attitude,
            trajectory_timestamps,
            trajectory_values,
            render_timestamps,
            deploy,
            landing,
            event_frame_indices,
            phase_segments=tuple(
                TrajectoryPhaseSegment(segment.phase, segment.timestamp_us, segment.values - origin)
                for segment in TrajectoryPhaseSegments_Build(
                    geometry_position, (() if deploy is None else (deploy,)),
                    start_timestamp_us=start,
                    end_timestamp_us=resolved_mission.end_timestamp_us,
                )
            ),
        )
        full_values = np.asarray(
            (resolved_bounds.min_enu, resolved_bounds.max_enu),
            dtype=np.float64,
        )
        ground_bounds = self._TrajectoryGroundPlaneBounds_Get(full_values)
        deploy_size, _, landing_size = TrajectoryMarkerWorldSizesFromExtent_Get(
            resolved_bounds.max_span
        )
        deploy_mesh: tuple[np.ndarray, np.ndarray] | None = None
        if deploy is not None:
            deploy_point = self._Position_At(geometry_position, deploy)
            if deploy_point is not None:
                deploy_mesh = TrajectoryEventMesh_Get(
                    np.asarray(deploy_point, dtype=np.float64) - origin,
                    deploy_size,
                )
        landing_mesh: tuple[np.ndarray, np.ndarray] | None = None
        if landing is not None:
            landing_point = self._Position_NearEvent(geometry_position, landing)
            if landing_point is not None:
                landing_mesh = TrajectoryEventMesh_Get(
                    np.asarray(landing_point, dtype=np.float64) - origin,
                    landing_size,
                )

        background, foreground, _ = self._Plot_Configure(theme)
        labels = _LABELS[language]
        frames: list[Image.Image] = []
        figure: Any | None = None

        try:
            figure = plt.figure(figsize=(10, 5), dpi=90)
            figure.patch.set_facecolor(background)
            attitude_axis = figure.add_subplot(121, projection="3d")
            trajectory_axis = figure.add_subplot(122, projection="3d")
            rocket = self._Attitude_AxisDraw(
                attitude_axis,
                frame_samples[0].quaternion,
                language,
                theme,
            )
            trajectory_artists = self._ReplayTrajectoryArtists_Create(
                trajectory_axis,
                language,
                theme,
                full_values,
                ground_bounds,
                deploy_mesh,
                landing_mesh,
            )
            time_title = figure.suptitle("", color=foreground, fontsize=12)
            figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))

            for frame_number, sample in enumerate(frame_samples):
                progress.context.Cancel_RaiseIfRequested()
                rocket.set_verts(
                    self._RocketPolygons_Get(sample.quaternion)
                )
                self._ReplayTrajectoryArtists_Update(
                    trajectory_artists,
                    sample,
                )
                elapsed = (sample.timestamp_us - start) * 1.0e-6
                time_title.set_text(
                    f"{labels['time']}: {elapsed:.3f} s",
                )
                figure.canvas.draw()
                rgba = np.asarray(figure.canvas.buffer_rgba(), dtype=np.uint8).copy()
                frame = Image.fromarray(rgba).convert(
                    "P",
                    palette=Image.Palette.ADAPTIVE,
                    colors=254,
                )
                self._GifFrameSequenceTag_Apply(frame, frame_number)
                frames.append(frame)
                progress.Unit_Complete("export.running")

            final_frame = frames[-1]
            for _ in range(_REPLAY_FINAL_HOLD_FRAME_COUNT - 1):
                progress.context.Cancel_RaiseIfRequested()
                hold_frame = final_frame.copy()
                self._GifFrameSequenceTag_Apply(hold_frame, len(frames))
                frames.append(hold_frame)
                progress.Unit_Complete("export.running")

            progress.context.Cancel_RaiseIfRequested()
            durations_ms = self._ReplayFrameDurations_Get(
                int(frame_timestamps.size),
                terminal_timestamp - effective_start,
            )
            frames[0].save(
                path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations_ms,
                loop=0,
                disposal=2,
                optimize=False,
            )
        finally:
            if figure is not None:
                plt.close(figure)
            for frame in frames:
                frame.close()
