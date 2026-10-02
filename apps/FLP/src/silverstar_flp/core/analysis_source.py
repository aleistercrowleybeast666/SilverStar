from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.mission import (
    MissionReplayBounds,
)
from silverstar_flp.core.mission import (
    MissionReplayBounds_Get as _MissionReplayBounds_Get,
)
from silverstar_flp.core.trajectory import TrajectoryBounds, TrajectoryBounds_Calculate
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmResult,
    ReplayFidelity,
    ReplayMode,
)


class AnalysisSourceKind(StrEnum):
    RECORDED = "recorded"
    RECOMPUTED = "recomputed"
    WHAT_IF = "what_if"


@dataclass(frozen=True, slots=True)
class AnalysisSource:
    source_id: str
    kind: AnalysisSourceKind
    algorithm_id: str | None = None
    result_id: str | None = None
    analysis_only: bool = False


@dataclass(frozen=True, slots=True)
class RecordedSolutionLayer:
    solution_id: str
    algorithm_id: str
    channel_id: str
    series: TimeSeries


@dataclass(frozen=True, slots=True)
class ReplayStoredResult:
    result_id: str
    source_id: str
    run_index: int
    algorithm_name: str
    algorithm_id: str
    algorithm_version: str
    mode: ReplayMode
    input_source: str
    parameters: Mapping[str, object]
    fidelity: ReplayFidelity
    warnings: tuple[str, ...]
    channels: Mapping[str, TimeSeries]
    diagnostics: Mapping[str, object]
    result: AlgorithmResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "channels", MappingProxyType(dict(self.channels)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))

    @property
    def analysis_only(self) -> bool:
        return self.diagnostics.get("offline_diagnostics", {}).get("mode") == "analysis_only"

    @property
    def kind(self) -> AnalysisSourceKind:
        return (
            AnalysisSourceKind.WHAT_IF
            if self.mode == ReplayMode.WHAT_IF
            else AnalysisSourceKind.RECOMPUTED
        )

    @property
    def sample_count(self) -> int:
        return max((series.count for series in self.channels.values()), default=0)

    @property
    def analysis_ready(self) -> bool:
        required = (
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        )
        return (
            self.fidelity != ReplayFidelity.UNAVAILABLE
            and not self.result.missing_inputs
            and all(
                (series := self.channels.get(channel_id)) is not None
                and series.count > 0
                and bool(series.valid.any())
                for channel_id in required
            )
        )

    @property
    def time_coverage_us(self) -> tuple[int, int] | None:
        starts = [int(series.timestamp_us[0]) for series in self.channels.values() if series.count]
        ends = [int(series.timestamp_us[-1]) for series in self.channels.values() if series.count]
        if not starts or not ends:
            return None
        return min(starts), max(ends)

    def StableName_Get(self) -> str:
        mode = (
            "Analysis-only"
            if self.analysis_only
            else ("What-if" if self.mode == ReplayMode.WHAT_IF else "Recomputed")
        )
        return f"{self.algorithm_name} / {mode} #{self.run_index}"


class ReplayResultStore:
    RECORDED_SOURCE_ID = "recorded"

    def __init__(self) -> None:
        self._entries: list[ReplayStoredResult] = []
        self._by_result_id: dict[str, ReplayStoredResult] = {}
        self._by_source_id: dict[str, ReplayStoredResult] = {}
        self._active_source_id = self.RECORDED_SOURCE_ID

    def Clear(self) -> None:
        self._entries.clear()
        self._by_result_id.clear()
        self._by_source_id.clear()
        self._active_source_id = self.RECORDED_SOURCE_ID

    def Result_Add(
        self,
        result: AlgorithmResult,
        *,
        algorithm_name: str | None = None,
        restored_run_index: int | None = None,
    ) -> ReplayStoredResult:
        if result.provenance == "Integrity-assisted KF6":
            raise ValueError("legacy_integrity_assistance_result_unsupported")
        mode = (
            ReplayMode.WHAT_IF
            if result.provenance == "What-if"
            else (
                ReplayMode.OFFLINE
                if result.provenance == "Offline"
                else ReplayMode.RECORDED_CONFIGURATION
            )
        )
        run_index = restored_run_index if restored_run_index is not None else 1 + max(
            (entry.run_index for entry in self._entries
             if entry.algorithm_id == result.algorithm_id and entry.mode == mode), default=0)
        if type(run_index) is not int or run_index <= 0:
            raise ValueError("replay_result_identity_invalid")
        algorithm_key = result.algorithm_id.rsplit(".", 1)[-1]
        mode_key = {
            ReplayMode.WHAT_IF: "what_if",
            ReplayMode.OFFLINE: "offline",
            ReplayMode.RECORDED_CONFIGURATION: "recomputed",
        }[mode]
        result_id = f"{algorithm_key}:{mode_key}:{run_index}"
        source_id = f"replay:{result_id}"
        if result_id in self._by_result_id:
            raise ValueError("replay_result_identity_duplicate")
        entry = ReplayStoredResult(
            result_id=result_id,
            source_id=source_id,
            run_index=run_index,
            algorithm_name=algorithm_name or algorithm_key,
            algorithm_id=result.algorithm_id,
            algorithm_version=result.algorithm_version,
            mode=mode,
            input_source=result.input_source,
            parameters=dict(result.parameters),
            fidelity=result.fidelity,
            warnings=tuple(result.warnings),
            channels=dict(result.channels),
            diagnostics=dict(result.diagnostics),
            result=result,
        )
        self._entries.append(entry)
        self._by_result_id[result_id] = entry
        self._by_source_id[source_id] = entry
        return entry

    def Entries_Get(self) -> tuple[ReplayStoredResult, ...]:
        return tuple(self._entries)

    def Entry_Get(self, result_id: str) -> ReplayStoredResult | None:
        return self._by_result_id.get(result_id)

    def SourceEntry_Get(self, source_id: str) -> ReplayStoredResult | None:
        return self._by_source_id.get(source_id)

    def Snapshot_Create(self, source_id: str) -> ReplayResultStore:
        snapshot = ReplayResultStore()
        if source_id == self.RECORDED_SOURCE_ID:
            return snapshot
        entry = self.SourceEntry_Get(source_id)
        if entry is None or not entry.analysis_ready:
            raise ValueError(f"export_source_unavailable:{source_id}")
        snapshot._entries.append(entry)
        snapshot._by_result_id[entry.result_id] = entry
        snapshot._by_source_id[entry.source_id] = entry
        snapshot._active_source_id = entry.source_id
        return snapshot

    def Sources_Get(self) -> tuple[AnalysisSource, ...]:
        sources = [AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)]
        sources.extend(
            AnalysisSource(
                entry.source_id,
                entry.kind,
                entry.algorithm_id,
                entry.result_id,
                entry.analysis_only,
            )
            for entry in self._entries
            if entry.analysis_ready
        )
        return tuple(sources)

    def ActiveSource_Get(self) -> AnalysisSource:
        if self._active_source_id == self.RECORDED_SOURCE_ID:
            return AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)
        entry = self._by_source_id.get(self._active_source_id)
        if entry is None or not entry.analysis_ready:
            self._active_source_id = self.RECORDED_SOURCE_ID
            return AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)
        return AnalysisSource(
            entry.source_id, entry.kind, entry.algorithm_id, entry.result_id, entry.analysis_only
        )

    def ActiveSource_Set(self, source_id: str) -> bool:
        if source_id != self.RECORDED_SOURCE_ID:
            entry = self._by_source_id.get(source_id)
            if entry is None or not entry.analysis_ready:
                return False
        self._active_source_id = source_id
        return True


class ChannelResolver:
    _ESTIMATOR_DIAGNOSTIC_QUANTITIES = frozenset(
        {"covariance", "innovation", "nis", "update_result"}
    )
    _RECORDED_DIRECT = {
        "attitude.q_nb": "pure_ins.recorded.attitude.q_nb",
        "navigation.linear_accel_enu": "pure_ins.recorded.navigation.linear_accel_enu",
        "imu.corrected.accel_b": "imu.corrected.accel_b",
        "imu.corrected.gyro_b": "imu.corrected.gyro_b",
    }

    def __init__(self, dataset: FlightDataset, store: ReplayResultStore) -> None:
        self.dataset = dataset
        self.store = store
        self._mission_bounds_cache: dict[str, MissionReplayBounds] = {}
        self._trajectory_bounds_cache: dict[str, TrajectoryBounds] = {}
        self._trajectory_bounds_calculation_count: dict[str, int] = {}
        self._TrajectoryBounds_Prime()

    @staticmethod
    def _SeriesValidEndTimestamp_Get(series: TimeSeries | None) -> int | None:
        if series is None or series.count == 0:
            return None
        valid_indices = series.valid.nonzero()[0]
        if valid_indices.size == 0:
            return None
        return int(series.timestamp_us[valid_indices[-1]])

    def _RecordedPositionSolution_Get(self) -> str | None:
        for solution in ("sf6", "eskf15", "kf6", "pure_ins"):
            if self.RecordedSeries_Get(
                "navigation.position_enu",
                solution=solution,
            ) is not None:
                return solution
        return None

    def _SourceCacheKey_Get(
        self,
        source_id: str | None,
        solution: str | None,
    ) -> tuple[str, AnalysisSource, str | None]:
        source = self.Source_Get(source_id)
        if source.kind != AnalysisSourceKind.RECORDED:
            return source.source_id, source, None
        resolved_solution = solution or self._RecordedPositionSolution_Get()
        cache_suffix = resolved_solution or "unavailable"
        return f"recorded:{cache_suffix}", source, resolved_solution

    def MissionReplayBounds_Get(
        self,
        source_id: str | None = None,
        *,
        solution: str | None = None,
    ) -> MissionReplayBounds:
        key, source, resolved_solution = self._SourceCacheKey_Get(source_id, solution)
        cached = self._mission_bounds_cache.get(key)
        if cached is not None:
            return cached
        if source.kind == AnalysisSourceKind.RECORDED:
            candidates = (
                self.RecordedSeries_Get(
                    "navigation.position_enu",
                    solution=resolved_solution,
                ),
                self.RecordedSeries_Get("attitude.q_nb"),
            )
        else:
            candidates = (
                self.Series_Get("navigation.position_enu", source.source_id),
                self.Series_Get("attitude.q_nb", source.source_id),
            )
        source_ends = tuple(
            timestamp
            for series in candidates
            if (timestamp := self._SeriesValidEndTimestamp_Get(series)) is not None
        )
        bounds = _MissionReplayBounds_Get(
            self.dataset,
            source_end_timestamp_us=max(source_ends, default=None),
        )
        self._mission_bounds_cache[key] = bounds
        return bounds

    def TrajectoryBounds_Get(
        self,
        source_id: str | None = None,
        *,
        solution: str | None = None,
    ) -> TrajectoryBounds | None:
        key, source, resolved_solution = self._SourceCacheKey_Get(source_id, solution)
        cached = self._trajectory_bounds_cache.get(key)
        if cached is not None:
            return cached
        if source.kind == AnalysisSourceKind.RECORDED:
            position = self.RecordedSeries_Get(
                "navigation.position_enu",
                solution=resolved_solution,
            )
        else:
            position = self.Series_Get("navigation.position_enu", source.source_id)
        if position is None or position.count == 0:
            return None
        bounds = TrajectoryBounds_Calculate(
            position,
            self.MissionReplayBounds_Get(
                source.source_id,
                solution=resolved_solution,
            ),
        )
        self._trajectory_bounds_cache[key] = bounds
        self._trajectory_bounds_calculation_count[key] = (
            self._trajectory_bounds_calculation_count.get(key, 0) + 1
        )
        return bounds

    def TrajectoryBoundsCalculationCount_Get(
        self,
        source_id: str | None = None,
        *,
        solution: str | None = None,
    ) -> int:
        key, _, _ = self._SourceCacheKey_Get(source_id, solution)
        return self._trajectory_bounds_calculation_count.get(key, 0)

    def _TrajectoryBounds_Prime(self) -> None:
        for solution in ("pure_ins", "kf6", "eskf15", "sf6"):
            self.TrajectoryBounds_Get(
                ReplayResultStore.RECORDED_SOURCE_ID,
                solution=solution,
            )
        for entry in self.store.Entries_Get():
            if entry.analysis_ready:
                self.TrajectoryBounds_Get(entry.source_id)

    def Source_Get(self, source_id: str | None = None) -> AnalysisSource:
        if source_id is None:
            return self.store.ActiveSource_Get()
        if source_id == ReplayResultStore.RECORDED_SOURCE_ID:
            return AnalysisSource(source_id, AnalysisSourceKind.RECORDED)
        entry = self.store.SourceEntry_Get(source_id)
        if entry is None:
            return AnalysisSource(
                ReplayResultStore.RECORDED_SOURCE_ID,
                AnalysisSourceKind.RECORDED,
            )
        return AnalysisSource(
            entry.source_id, entry.kind, entry.algorithm_id, entry.result_id, entry.analysis_only
        )

    def Series_Get(self, channel_id: str, source_id: str | None = None) -> TimeSeries | None:
        source = self.Source_Get(source_id)
        if source.kind == AnalysisSourceKind.RECORDED:
            return self.RecordedSeries_Get(channel_id)
        entry = self.store.SourceEntry_Get(source.source_id)
        if entry is None:
            return None
        return entry.channels.get(channel_id)

    def RecordedSeries_Get(
        self,
        channel_id: str,
        *,
        solution: str | None = None,
    ) -> TimeSeries | None:
        if channel_id in ("navigation.position_enu", "navigation.velocity_enu"):
            suffix = channel_id.removeprefix("navigation.")
            prefixes = {
                "pure_ins": ("pure_ins.recorded.navigation",),
                "kf6": ("kf6.recorded.navigation",),
                "eskf15": ("eskf15.recorded.navigation",),
                "sf6": ("sf6.recorded.navigation",),
                "final": ("sf6.recorded.navigation", "eskf15.recorded.navigation", "kf6.recorded.navigation"),
                None: (
                    "sf6.recorded.navigation",
                    "eskf15.recorded.navigation",
                    "kf6.recorded.navigation",
                    "pure_ins.recorded.navigation",
                ),
            }.get(solution, ())
            for prefix in prefixes:
                series = self.dataset.Series_Get(f"{prefix}.{suffix}")
                if series is not None:
                    breaks = []
                    previous = (0, 0, 0, 0)
                    for record in self.dataset.Records_Get("GNSS_RECOVERY"):
                        counts = record.payload["reanchor_count"]
                        if any(a > b for a, b in zip(counts, previous, strict=True)):
                            breaks.append(record.payload["estimator_present_timestamp_us"])
                        previous = counts
                    if breaks and prefix.startswith("kf6"):
                        return replace(series, metadata={**series.metadata,
                                       "discontinuity_timestamps_us": tuple(breaks)})
                    return series
            return None
        if channel_id in ("attitude.q_nb", "navigation.linear_accel_enu"):
            selected = solution or self._RecordedPositionSolution_Get()
            return (
                self.dataset.Series_Get(f"{selected}.recorded.{channel_id}") if selected else None
            )
        direct_series = self.dataset.Series_Get(channel_id)
        if direct_series is not None:
            return direct_series
        direct_id = self._RECORDED_DIRECT.get(channel_id)
        if direct_id is not None:
            return self.dataset.Series_Get(direct_id)
        namespace, separator, remainder = channel_id.partition(".")
        if separator:
            return self.dataset.Series_Get(f"{namespace}.recorded.{remainder}")
        return None

    def RecordedSolutionLayers_Get(
        self,
        channel_id: str,
    ) -> tuple[RecordedSolutionLayer, ...]:
        if channel_id not in ("navigation.position_enu", "navigation.velocity_enu"):
            series = self.RecordedSeries_Get(channel_id)
            if series is None:
                return ()
            return (
                RecordedSolutionLayer(
                    "recorded",
                    "silverstar.recorded",
                    channel_id,
                    series,
                ),
            )
        layers: list[RecordedSolutionLayer] = []
        for solution_id, algorithm_id in (
            ("pure_ins", "silverstar.algorithm.pure_ins"),
            ("kf6", "silverstar.algorithm.kf6"),
            ("eskf15", "silverstar.algorithm.estimator.eskf15"),
            ("sf6", "silverstar.algorithm.estimator.sf6"),
        ):
            series = self.RecordedSeries_Get(channel_id, solution=solution_id)
            if series is not None:
                layers.append(
                    RecordedSolutionLayer(
                        solution_id,
                        algorithm_id,
                        channel_id,
                        series,
                    )
                )
        return tuple(layers)

    def RecordedNavigationSources_Get(self) -> tuple[str, ...]:
        sources: list[str] = []
        if self.RecordedSeries_Get(
            "navigation.position_enu", solution="pure_ins"
        ) is not None:
            sources.append("Pure INS")
        if self.RecordedSeries_Get(
            "navigation.position_enu", solution="kf6"
        ) is not None:
            sources.append("KF_6")
        if self.RecordedSeries_Get(
            "navigation.position_enu", solution="eskf15"
        ) is not None:
            sources.append("ESKF_15")
        if self.RecordedSeries_Get("navigation.position_enu", solution="sf6") is not None:
            sources.append("SF6")
        return tuple(sources)

    def RecordedNavigationSource_Get(self) -> str:
        if self.RecordedSeries_Get("navigation.position_enu", solution="sf6") is not None:
            return "SF6"
        if self.RecordedSeries_Get("navigation.position_enu", solution="eskf15") is not None:
            return "ESKF_15"
        if any(
            self.dataset.Series_Get(channel_id) is not None
            for channel_id in (
                "kf6.recorded.navigation.position_enu",
                "kf6.recorded.navigation.velocity_enu",
            )
        ):
            return "KF_6"
        if any(
            self.dataset.Series_Get(channel_id) is not None
            for channel_id in (
                "pure_ins.recorded.navigation.position_enu",
                "pure_ins.recorded.navigation.velocity_enu",
            )
        ):
            return "Pure INS"
        return "N/A"

    def EstimatorSources_Get(
        self,
        estimator_algorithm_ids: Iterable[str] = (),
    ) -> tuple[AnalysisSource, ...]:
        algorithm_ids = tuple(dict.fromkeys(estimator_algorithm_ids))
        if not algorithm_ids:
            replay_ids = tuple(
                entry.algorithm_id
                for entry in self.store.Entries_Get()
                if any(
                    series.quantity in self._ESTIMATOR_DIAGNOSTIC_QUANTITIES
                    for series in entry.channels.values()
                )
            )
            recorded_namespaces = tuple(
                channel_id.partition(".recorded.")[0]
                for channel_id, series in self.dataset.series.items()
                if ".recorded." in channel_id
                and series.quantity in self._ESTIMATOR_DIAGNOSTIC_QUANTITIES
            )
            algorithm_ids = tuple(
                dict.fromkeys(
                    (*replay_ids, *(f"silverstar.algorithm.{name}" for name in recorded_namespaces))
                )
            )
        sources: list[AnalysisSource] = []
        for algorithm_id in algorithm_ids:
            namespace = algorithm_id.rsplit(".", 1)[-1]
            if any(
                channel_id.startswith(f"{namespace}.recorded.")
                for channel_id in self.dataset.series
            ):
                sources.append(
                    AnalysisSource(
                        ReplayResultStore.RECORDED_SOURCE_ID,
                        AnalysisSourceKind.RECORDED,
                        algorithm_id,
                    )
                )
        for entry in self.store.Entries_Get():
            if entry.algorithm_id in algorithm_ids:
                sources.append(
                    AnalysisSource(
                        entry.source_id,
                        entry.kind,
                        entry.algorithm_id,
                        entry.result_id,
                    )
                )
        return tuple(sources)

    def ExplorerChannels_Get(self) -> dict[str, TimeSeries]:
        channels = dict(self.dataset.series)
        for entry in self.store.Entries_Get():
            prefix = entry.StableName_Get()
            for channel_id, series in entry.channels.items():
                channels[f"{prefix} / {channel_id}"] = series
        return channels
