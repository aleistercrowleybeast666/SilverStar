from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.decoder_profiles.descriptor import DecoderProfileDescriptor
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.package import (
    DecoderPackageLimits,
    DecoderProfilePackage,
)
from silverstar_flp.plugins.api.log_container import (
    ContainerError,
    LogContainerPlugin,
    ParseOptions,
)

_LOG_SUFFIXES = frozenset({".sslog", ".bin"})


@dataclass(frozen=True, slots=True)
class DiscoveryLimits:
    maximum_depth: int = 5
    maximum_parent_levels: int = 5
    maximum_file_count: int = 10_000
    maximum_total_file_bytes: int = 8 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TaskDirectoryDiscovery:
    selected_path: Path
    log_paths: tuple[Path, ...]
    decoder_package_paths: tuple[Path, ...]
    scanned_file_count: int
    scanned_total_bytes: int
    limit_reached: bool


@dataclass(frozen=True, slots=True)
class DecoderProfileMatch:
    package: DecoderProfilePackage
    reason: str
    descriptor: DecoderProfileDescriptor


@dataclass(frozen=True, slots=True)
class DecoderProfileMatchResult:
    matches: tuple[DecoderProfileMatch, ...]
    errors: Mapping[Path, str]
    descriptor_found: bool


@dataclass(frozen=True, slots=True)
class DecoderProfileCacheReference:
    generation_profile_sha256: str
    package_sha256: str
    relative_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "generation_profile_sha256": self.generation_profile_sha256,
            "package_sha256": self.package_sha256,
            "relative_path": self.relative_path,
        }


class TaskDirectoryScanner:
    def __init__(self, limits: DiscoveryLimits | None = None) -> None:
        self.limits = limits or DiscoveryLimits()

    def Scan(self, selected_path: Path) -> TaskDirectoryDiscovery:
        selected = Path(selected_path)
        scan_root = selected.parent if selected.is_file() else selected
        if not scan_root.is_dir():
            raise DecoderProfileError("decoder_discovery_directory_invalid", str(scan_root))
        log_paths: set[Path] = set()
        package_paths: set[Path] = set()
        scanned_count = 0
        scanned_bytes = 0
        limit_reached = False
        pending: list[tuple[Path, int]] = [(scan_root, 0)]
        while pending:
            directory, depth = pending.pop()
            try:
                entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                continue
            for entry in entries:
                if entry.is_symlink():
                    continue
                try:
                    if entry.is_dir():
                        if depth < self.limits.maximum_depth:
                            pending.append((entry, depth + 1))
                        continue
                    if not entry.is_file():
                        continue
                    file_size = entry.stat().st_size
                except OSError:
                    continue
                scanned_count += 1
                scanned_bytes += file_size
                if (
                    scanned_count > self.limits.maximum_file_count
                    or scanned_bytes > self.limits.maximum_total_file_bytes
                ):
                    limit_reached = True
                    pending.clear()
                    break
                suffix = entry.suffix.casefold()
                if suffix in _LOG_SUFFIXES:
                    log_paths.add(entry.resolve())
                elif suffix == ".ssdecoder":
                    package_paths.add(entry.resolve())

        ancestor = scan_root
        for _ in range(self.limits.maximum_parent_levels + 1):
            try:
                for candidate in ancestor.glob("*.ssdecoder"):
                    if candidate.is_file() and not candidate.is_symlink():
                        package_paths.add(candidate.resolve())
            except OSError:
                pass
            parent = ancestor.parent
            if parent == ancestor:
                break
            ancestor = parent
        if selected.is_file() and selected.suffix.casefold() in _LOG_SUFFIXES:
            log_paths.add(selected.resolve())
        return TaskDirectoryDiscovery(
            selected_path=selected,
            log_paths=tuple(sorted(log_paths, key=lambda item: str(item).casefold())),
            decoder_package_paths=tuple(
                sorted(package_paths, key=lambda item: str(item).casefold())
            ),
            scanned_file_count=scanned_count,
            scanned_total_bytes=scanned_bytes,
            limit_reached=limit_reached,
        )


class DecoderProfileMatcher:
    def __init__(
        self,
        container_plugins: Mapping[str, LogContainerPlugin],
        *,
        package_limits: DecoderPackageLimits | None = None,
    ) -> None:
        self.container_plugins = dict(container_plugins)
        self.package_limits = package_limits

    def Match(
        self,
        log_path: Path,
        candidate_paths: Sequence[Path],
    ) -> DecoderProfileMatchResult:
        matches: list[DecoderProfileMatch] = []
        errors: dict[Path, str] = {}
        descriptor_found = False
        seen_packages: set[str] = set()
        for candidate_path in candidate_paths:
            source_path = Path(candidate_path)
            try:
                package = DecoderProfilePackage.Load(
                    source_path,
                    limits=self.package_limits,
                    container_plugins=self.container_plugins,
                )
                if package.package_sha256 in seen_packages:
                    continue
                seen_packages.add(package.package_sha256)
                container = self.container_plugins[package.required_container_plugin_id]
                descriptor = self.Descriptor_Read(Path(log_path), container)
                descriptor_found = True
                descriptor.PackageExactMatch_Validate(package)
                matches.append(
                    DecoderProfileMatch(
                        package=package,
                        reason="exact_generation_profile",
                        descriptor=descriptor,
                    )
                )
            except (ContainerError, DecoderProfileError, OSError) as exc:
                errors[source_path] = str(exc)
        matches.sort(
            key=lambda item: str(item.package.source_path).casefold()
        )
        return DecoderProfileMatchResult(
            matches=tuple(matches),
            errors=errors,
            descriptor_found=descriptor_found,
        )

    @staticmethod
    def Descriptor_Read(
        log_path: Path,
        container: LogContainerPlugin,
    ) -> DecoderProfileDescriptor:
        diagnostics = ParserDiagnostics()
        descriptor: DecoderProfileDescriptor | None = None
        with log_path.open("rb") as source:
            probe = container.probe(source)
            if probe.confidence <= 0.0:
                raise DecoderProfileError(
                    "decoder_container_probe_failed",
                    str(log_path),
                )
            source.seek(0)
            options = ParseOptions(
                diagnostics=diagnostics,
                source_size=log_path.stat().st_size,
            )
            container.header_read(source, options)
            for frame in container.iter_frames(source, options):
                current = DecoderProfileDescriptor.FromRawPayload(
                    frame.record_type,
                    frame.record_version,
                    frame.payload_bytes,
                )
                if current is None:
                    continue
                if descriptor is not None and current != descriptor:
                    raise DecoderProfileError(
                        "decoder_profile_descriptor_conflict"
                    )
                descriptor = current
        if descriptor is None:
            raise DecoderProfileError("decoder_profile_descriptor_missing")
        return descriptor


class DecoderProfileCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else self.DefaultRoot_Get()

    @staticmethod
    def DefaultRoot_Get() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "SilverStar" / "FLP" / "decoder_profiles"

    def Package_Import(
        self,
        source_path: Path,
        *,
        container_plugins: Mapping[str, LogContainerPlugin],
        limits: DecoderPackageLimits | None = None,
    ) -> tuple[DecoderProfilePackage, DecoderProfileCacheReference]:
        package = DecoderProfilePackage.Load(
            Path(source_path),
            limits=limits,
            container_plugins=container_plugins,
        )
        generation_directory = self.root / package.generation_profile_sha256[:32]
        target_path = generation_directory / (
            f"{package.package_sha256[:32]}.ssdecoder"
        )
        self._Target_Validate(target_path)
        generation_directory.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            cached = DecoderProfilePackage.Load(
                target_path,
                limits=limits,
                container_plugins=container_plugins,
            )
            if cached.package_sha256 != package.package_sha256:
                raise DecoderProfileError("decoder_cache_hash_conflict")
        else:
            temporary_path = generation_directory / f".import-{uuid.uuid4().hex[:8]}.tmp"
            self._Target_Validate(temporary_path)
            try:
                shutil.copyfile(package.source_path, temporary_path)
                copied_hash = _FileSha256_Get(temporary_path)
                if copied_hash != package.package_sha256:
                    raise DecoderProfileError("decoder_cache_copy_hash_mismatch")
                os.replace(temporary_path, target_path)
            finally:
                with contextlib.suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
        cached_package = DecoderProfilePackage.Load(
            target_path,
            limits=limits,
            container_plugins=container_plugins,
        )
        reference = DecoderProfileCacheReference(
            generation_profile_sha256=package.generation_profile_sha256,
            package_sha256=package.package_sha256,
            relative_path=target_path.relative_to(self.root).as_posix(),
        )
        return cached_package, reference

    def Package_Load(
        self,
        reference: DecoderProfileCacheReference,
        *,
        container_plugins: Mapping[str, LogContainerPlugin],
        limits: DecoderPackageLimits | None = None,
    ) -> DecoderProfilePackage:
        expected_path = (
            self.root
            / reference.generation_profile_sha256[:32]
            / f"{reference.package_sha256[:32]}.ssdecoder"
        )
        self._Target_Validate(expected_path)
        package = DecoderProfilePackage.Load(
            expected_path,
            limits=limits,
            container_plugins=container_plugins,
        )
        if (
            package.generation_profile_sha256
            != reference.generation_profile_sha256
            or package.package_sha256 != reference.package_sha256
        ):
            raise DecoderProfileError("decoder_cache_reference_mismatch")
        return package

    def _Target_Validate(self, target_path: Path) -> None:
        resolved_root = self.root.resolve()
        resolved_target = target_path.resolve()
        if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
            raise DecoderProfileError("decoder_cache_target_outside_root")


def _FileSha256_Get(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
