from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.diagnostics import DataQualitySummary, ParserDiagnostics
from silverstar_flp.decoder_profiles.descriptor import DecoderProfileDescriptor
from silverstar_flp.decoder_profiles.discovery import (
    DecoderProfileCache,
    DecoderProfileCacheReference,
    DecoderProfileMatcher,
    TaskDirectoryDiscovery,
    TaskDirectoryScanner,
)
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.package import (
    DecoderPackageLimits,
    DecoderProfilePackage,
)
from silverstar_flp.decoder_profiles.parser import DecoderProfileParserPlugin
from silverstar_flp.decoder_profiles.semantic_adapter import (
    LoggingProtocol_Validate,
    SilverStarSslog0SemanticAdapter,
)
from silverstar_flp.plugins.api.log_container import LogContainerPlugin
from silverstar_flp.plugins.registry import PluginRegistry

_LOG_SUFFIXES = frozenset({".bin", ".sslog"})


class LogOpenSourceMode(StrEnum):
    MANUAL = "manual"
    FOLDER_SEARCH = "folder_search"
    AUTO_FIND = "folder_search"
    DRAG_DROP = "drag_drop"
    PROJECT = "project"
    CLI = "cli"


@dataclass(frozen=True, slots=True)
class LogOpenRequest:
    log_path: Path
    decoder_package_path: Path | None = None
    cache_reference: DecoderProfileCacheReference | None = None
    auto_find: bool = False
    task_directory: Path | None = None
    source_mode: LogOpenSourceMode = LogOpenSourceMode.MANUAL
    project_path: Path | None = None
    dataset_cache_reference: dict | None = None
    allow_unverified_decoder: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.log_path, (list, tuple, set, frozenset)):
            raise DecoderProfileError("multiple_logs_not_allowed")
        if isinstance(
            self.decoder_package_path,
            (list, tuple, set, frozenset),
        ):
            raise DecoderProfileError("multiple_decoder_packages_not_allowed")
        object.__setattr__(self, "log_path", Path(self.log_path))
        if self.decoder_package_path is not None:
            object.__setattr__(
                self,
                "decoder_package_path",
                Path(self.decoder_package_path),
            )
        if self.task_directory is not None:
            object.__setattr__(self, "task_directory", Path(self.task_directory))
        if type(self.allow_unverified_decoder) is not bool:
            raise ValueError("custom_decoder_opt_in_invalid")
        if self.allow_unverified_decoder and (
                self.decoder_package_path is None or self.auto_find or self.cache_reference is not None
                or self.source_mode != LogOpenSourceMode.MANUAL):
            raise ValueError("custom_decoder_requires_explicit_manual_pair")
        if self.auto_find and (
            self.decoder_package_path is not None
            or self.cache_reference is not None
        ):
            raise ValueError("log_open_decoder_source_conflict")


@dataclass(frozen=True, slots=True)
class LogPairCandidate:
    log_path: Path
    decoder_package_path: Path
    package_sha256: str
    generation_profile_sha256: str
    project_name: str
    firmware_version: str


@dataclass(frozen=True, slots=True)
class LogPairDiscovery:
    selected_path: Path
    pairs: tuple[LogPairCandidate, ...]
    diagnostics: tuple[str, ...]
    scanned_file_count: int
    scanned_total_bytes: int
    limit_reached: bool


@dataclass(frozen=True, slots=True)
class LogOpenResult:
    dataset: FlightDataset
    package: DecoderProfilePackage
    descriptor: DecoderProfileDescriptor | None
    cache_reference: DecoderProfileCacheReference | None
    source_package_path: Path
    parse_diagnostics: ParserDiagnostics
    data_quality: DataQualitySummary
    match_mode: str = "exact_generation_profile"


@dataclass(slots=True)
class LogOpenCoordinator:
    registry: PluginRegistry
    cache: DecoderProfileCache = field(default_factory=DecoderProfileCache)
    scanner: TaskDirectoryScanner = field(default_factory=TaskDirectoryScanner)
    package_limits: DecoderPackageLimits | None = None

    def _ContainerPlugins_Get(self) -> Mapping[str, LogContainerPlugin]:
        return {
            plugin.metadata.plugin_id: plugin
            for plugin in self.registry.log_containers
        }

    @staticmethod
    def _LogPath_Validate(path: Path) -> Path:
        resolved = Path(path).resolve()
        if resolved.suffix.casefold() not in _LOG_SUFFIXES:
            raise DecoderProfileError(
                "log_open_extension_unsupported",
                resolved.suffix,
            )
        if not resolved.is_file():
            raise DecoderProfileError("log_open_file_missing", str(resolved))
        return resolved

    @staticmethod
    def _PackagePath_Validate(path: Path) -> Path:
        resolved = Path(path).resolve()
        if resolved.suffix.casefold() != ".ssdecoder":
            raise DecoderProfileError(
                "decoder_package_extension_invalid",
                resolved.suffix,
            )
        if not resolved.is_file():
            raise DecoderProfileError(
                "decoder_package_open_failed",
                str(resolved),
            )
        return resolved

    def PairDiscovery_Run(
        self,
        selected_path: Path,
        *,
        target_log_path: Path | None = None,
    ) -> LogPairDiscovery:
        discovery: TaskDirectoryDiscovery = self.scanner.Scan(Path(selected_path))
        target = (
            self._LogPath_Validate(target_log_path)
            if target_log_path is not None
            else None
        )
        log_paths = (target,) if target is not None else discovery.log_paths
        containers = self._ContainerPlugins_Get()
        matcher = DecoderProfileMatcher(
            containers,
            package_limits=self.package_limits,
        )
        pairs: list[LogPairCandidate] = []
        diagnostics: list[str] = []
        if discovery.limit_reached:
            diagnostics.append("decoder_discovery_limit_reached")
        if not log_paths:
            diagnostics.append("decoder_discovery_log_missing")
        if not discovery.decoder_package_paths:
            diagnostics.append("decoder_discovery_package_missing")
        display_root = discovery.selected_path
        if display_root.is_file():
            display_root = display_root.parent
        for log_path in log_paths:
            try:
                log_label = log_path.relative_to(display_root.resolve()).as_posix()
            except ValueError:
                log_label = str(log_path)
            result = matcher.Match(
                log_path,
                discovery.decoder_package_paths,
            )
            if not result.descriptor_found:
                diagnostics.append(
                    f"{log_label}:decoder_profile_descriptor_missing"
                )
            for package_path, error in sorted(
                result.errors.items(),
                key=lambda item: str(item[0]).casefold(),
            ):
                diagnostics.append(
                    f"{log_label}:{package_path.name}:{error}"
                )
            if len(result.matches) > 1:
                diagnostics.append(
                    f"{log_label}:decoder_profile_match_ambiguous"
                )
                continue
            if len(result.matches) != 1:
                diagnostics.append(
                    f"{log_label}:decoder_profile_exact_match_missing"
                )
                continue
            match = result.matches[0]
            package = match.package
            pairs.append(
                LogPairCandidate(
                    log_path=log_path,
                    decoder_package_path=package.source_path.resolve(),
                    package_sha256=package.package_sha256,
                    generation_profile_sha256=package.generation_profile_sha256,
                    project_name=package.semantics.project_name,
                    firmware_version=package.semantics.firmware_version,
                )
            )
        return LogPairDiscovery(
            selected_path=Path(selected_path),
            pairs=tuple(
                sorted(
                    pairs,
                    key=lambda item: (
                        str(item.log_path).casefold(),
                        str(item.decoder_package_path).casefold(),
                    ),
                )
            ),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            scanned_file_count=discovery.scanned_file_count,
            scanned_total_bytes=discovery.scanned_total_bytes,
            limit_reached=discovery.limit_reached,
        )

    def Open(
        self,
        request: LogOpenRequest,
        context: TaskContext | None = None,
    ) -> LogOpenResult:
        task_context = context or TaskContext()
        log_path = self._LogPath_Validate(request.log_path)
        task_context.Progress_Report(0.02, "log_open.package")
        if request.allow_unverified_decoder:
            return self._OpenUserCustom(request, log_path, task_context)
        if request.auto_find:
            selected = request.task_directory or log_path.parent
            discovery = self.PairDiscovery_Run(
                selected,
                target_log_path=log_path,
            )
            if len(discovery.pairs) != 1:
                code = (
                    "decoder_profile_match_ambiguous"
                    if len(discovery.pairs) > 1
                    else "decoder_profile_exact_match_missing"
                )
                raise DecoderProfileError(
                    code,
                    "|".join(discovery.diagnostics),
                )
            package_path = discovery.pairs[0].decoder_package_path
            return self._OpenWithSourcePackage(
                log_path,
                package_path,
                task_context,
                cache_request=request,
            )

        containers = self._ContainerPlugins_Get()
        cached_package: DecoderProfilePackage | None = None
        cache_load_failed = False
        if request.cache_reference is not None:
            try:
                cached_package = self.cache.Package_Load(
                    request.cache_reference,
                    container_plugins=containers,
                    limits=self.package_limits,
                )
            except (DecoderProfileError, OSError):
                cache_load_failed = True
                if (
                    request.decoder_package_path is None
                    and request.source_mode != LogOpenSourceMode.PROJECT
                ):
                    raise
        if cached_package is not None:
            return self._OpenWithCachedPackage(
                log_path,
                cached_package,
                request.cache_reference,
                cached_package.source_path,
                task_context,
                cache_request=request,
            )
        if (
            request.source_mode == LogOpenSourceMode.PROJECT
            and cache_load_failed
            and (
                request.decoder_package_path is None
                or not request.decoder_package_path.is_file()
            )
        ):
            selected = request.task_directory or (
                request.decoder_package_path.parent
                if request.decoder_package_path is not None
                else log_path.parent
            )
            discovery = self.PairDiscovery_Run(
                selected,
                target_log_path=log_path,
            )
            if len(discovery.pairs) != 1:
                code = (
                    "decoder_profile_match_ambiguous"
                    if len(discovery.pairs) > 1
                    else "decoder_profile_exact_match_missing"
                )
                raise DecoderProfileError(
                    code,
                    "|".join(discovery.diagnostics),
                )
            return self._OpenWithSourcePackage(
                log_path,
                discovery.pairs[0].decoder_package_path,
                task_context,
                cache_request=request,
            )
        if request.decoder_package_path is None:
            raise DecoderProfileError("decoder_package_path_required")
        package_path = self._PackagePath_Validate(request.decoder_package_path)
        return self._OpenWithSourcePackage(
            log_path,
            package_path,
            task_context,
            cache_request=request,
        )

    def _OpenUserCustom(self, request, log_path, context):
        """Explicit read-only view. No exact cache, semantic adapter, or replay admission."""
        from silverstar_flp.core.artifacts import FileHash_Get
        containers = self._ContainerPlugins_Get()
        package_path = self._PackagePath_Validate(request.decoder_package_path)
        package = DecoderProfilePackage.Load(package_path, limits=self.package_limits,
                                             container_plugins=containers)
        container = containers[package.required_container_plugin_id]
        source_hash = FileHash_Get(log_path)
        dataset = DecoderProfileParserPlugin(container, package,
                      allow_unverified_identity=True).parse(log_path, context)
        context.Cancel_RaiseIfRequested()
        if FileHash_Get(log_path) != source_hash:
            raise ValueError("log_source_changed_during_parse")
        dataset = replace(dataset, metadata={**dataset.metadata,
            "source_log_sha256": source_hash, "custom_decoder_unverified": True,
            "replay_allowed": False, "custom_decoder_source_path": str(package_path)})
        context.Progress_Report(1.0, "log_open.complete")
        return LogOpenResult(dataset, package, None, None, package_path,
                             dataset.diagnostics, dataset.data_quality,
                             match_mode="user_custom_unverified")

    def _OpenWithSourcePackage(
        self,
        log_path: Path,
        package_path: Path,
        context: TaskContext,
        *, cache_request: LogOpenRequest | None = None,
    ) -> LogOpenResult:
        containers = self._ContainerPlugins_Get()
        source_package = DecoderProfilePackage.Load(
            package_path,
            limits=self.package_limits,
            container_plugins=containers,
        )
        LoggingProtocol_Validate(source_package)
        container = containers[source_package.required_container_plugin_id]
        context.Progress_Report(0.10, "log_open.descriptor")
        descriptor = DecoderProfileMatcher.Descriptor_Read(log_path, container)
        descriptor.PackageExactMatch_Validate(source_package)
        context.Cancel_RaiseIfRequested()
        context.Progress_Report(0.18, "log_open.cache")
        cached_package, reference = self.cache.Package_Import(
            package_path,
            container_plugins=containers,
            limits=self.package_limits,
        )
        descriptor.PackageExactMatch_Validate(cached_package)
        return self._ParseAndAdapt(
            log_path,
            cached_package,
            descriptor,
            reference,
            package_path,
            context,
            cache_request=cache_request,
        )

    def _OpenWithCachedPackage(
        self,
        log_path: Path,
        package: DecoderProfilePackage,
        reference: DecoderProfileCacheReference,
        source_package_path: Path,
        context: TaskContext,
        *, cache_request: LogOpenRequest | None = None,
    ) -> LogOpenResult:
        containers = self._ContainerPlugins_Get()
        LoggingProtocol_Validate(package)
        container = containers[package.required_container_plugin_id]
        descriptor = DecoderProfileMatcher.Descriptor_Read(log_path, container)
        descriptor.PackageExactMatch_Validate(package)
        return self._ParseAndAdapt(
            log_path,
            package,
            descriptor,
            reference,
            source_package_path,
            context,
            cache_request=cache_request,
        )

    def _ParseAndAdapt(
        self,
        log_path: Path,
        package: DecoderProfilePackage,
        descriptor: DecoderProfileDescriptor,
        reference: DecoderProfileCacheReference,
        source_package_path: Path,
        context: TaskContext,
        *, cache_request: LogOpenRequest | None = None,
    ) -> LogOpenResult:
        containers = self._ContainerPlugins_Get()
        container = containers[package.required_container_plugin_id]
        from silverstar_flp.core.task_progress import TaskProgress
        progress = TaskProgress(context)
        from silverstar_flp.core.artifacts import FileHash_Get
        from silverstar_flp.core.parse_cache import ParseIdentity_Get
        from silverstar_flp.core.project import DecoderNumericalIdentity_Get
        progress.Progress_Report(0.22, "progress.open.source_check")
        identity = ParseIdentity_Get(log_path, DecoderNumericalIdentity_Get(package, container),
                                     progress.Context_Build(0.22, 0.28))
        parse_start = 0.28
        # Exact package validation and Descriptor matching have already succeeded.
        # Cache admission remains inside this coordinator, never a decoder fallback.
        if cache_request is not None and cache_request.dataset_cache_reference is not None:
            from silverstar_flp.core.parse_cache import DatasetCache_Read
            progress.Progress_Report(0.28, "progress.open.dataset_cache")
            parse_start = 0.50
            try:
                dataset = DatasetCache_Read(cache_request.project_path,
                    cache_request.dataset_cache_reference, identity, log_path,
                    progress.Context_Build(0.28, 0.50))
            except (ValueError, OSError, KeyError, TypeError, EOFError) as exc:
                logging.warning("Full dataset cache unavailable; strict parse follows: %s", exc)
            else:
                context.Cancel_RaiseIfRequested()
                progress.Progress_Report(0.96, "progress.open.source_check")
                if (FileHash_Get(log_path, progress.Context_Build(0.96, 0.99), quantified=True) != identity["log_sha256"]
                        or log_path.stat().st_size != identity["log_bytes"]):
                    raise ValueError("log_source_changed_during_parse")
                from silverstar_flp.decoder_profiles.fusion_timing_records import FusionTimingRecords_Validate
                FusionTimingRecords_Validate(dataset)
                progress.Progress_Report(1.0, "log_open.complete")
                return LogOpenResult(dataset, package, descriptor, reference,
                    Path(source_package_path), dataset.diagnostics, dataset.data_quality)
        progress.Progress_Report(parse_start, "log_open.parse")
        parser = DecoderProfileParserPlugin(container, package)
        parse_context = progress.Context_Build(parse_start, 0.94)
        dataset = parser.parse(log_path, parse_context)
        context.Cancel_RaiseIfRequested()
        progress.Progress_Report(0.94, "log_open.semantics")
        dataset = SilverStarSslog0SemanticAdapter(package).Apply(dataset)
        from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareMechanizationRecords_Validate
        FirmwareMechanizationRecords_Validate(dataset)
        from silverstar_flp.decoder_profiles.fusion_timing_records import FusionTimingRecords_Validate
        FusionTimingRecords_Validate(dataset)
        from silverstar_flp.decoder_profiles.sf6_revision import Sf6Revision_Get
        Sf6Revision_Get(dataset)
        progress.Progress_Report(0.96, "progress.open.source_check")
        if (FileHash_Get(log_path, progress.Context_Build(0.96, 0.99), quantified=True) != identity["log_sha256"]
                or log_path.stat().st_size != identity["log_bytes"]):
            raise ValueError("log_source_changed_during_parse")
        dataset = replace(dataset, metadata={**dataset.metadata,
                          "source_log_sha256": identity["log_sha256"],
                          "parse_identity": identity})
        progress.Progress_Report(1.0, "log_open.complete")
        return LogOpenResult(
            dataset=dataset,
            package=package,
            descriptor=descriptor,
            cache_reference=reference,
            source_package_path=Path(source_package_path),
            parse_diagnostics=dataset.diagnostics,
            data_quality=dataset.data_quality,
        )
