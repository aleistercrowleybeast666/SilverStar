from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.plugins.api.log_container import LogContainerPlugin

_PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_PLUGIN_VERSION_PATTERN = re.compile(
    r"^v?[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9_.-]+)?$"
)
_ENTRY_POINT_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$"
)
_PROTECTED_BUILTIN_IDS = frozenset({"silverstar.flight_log.container.0_0"})


@dataclass(frozen=True, slots=True)
class ContainerPluginPackageManifest:
    source_path: Path
    plugin_id: str
    version: str
    api_version: int
    entry_point: str
    package_sha256: str
    raw_manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ContainerPluginDiscovery:
    manifests: tuple[ContainerPluginPackageManifest, ...]
    errors: Mapping[Path, str]


class TrustedContainerPluginManager:
    """Manages explicitly installed code-plugin packages without auto-execution.

    A manifest is loaded only from the configured FLP plugin directory. Code is
    instantiated only through a host-provided trusted factory allowlist.
    """

    def __init__(
        self,
        plugin_directory: Path,
        *,
        api_version: int = 1,
        protected_plugin_ids: frozenset[str] = _PROTECTED_BUILTIN_IDS,
    ) -> None:
        self.plugin_directory = Path(plugin_directory)
        self.api_version = api_version
        self.protected_plugin_ids = protected_plugin_ids

    def Package_Install(
        self,
        source_path: Path,
        *,
        explicitly_trusted: bool,
    ) -> ContainerPluginPackageManifest:
        if not explicitly_trusted:
            raise DecoderProfileError("container_plugin_explicit_trust_required")
        source = Path(source_path)
        manifest = self._Manifest_Read(source, require_installed=False)
        if manifest.plugin_id in self.protected_plugin_ids:
            raise DecoderProfileError(
                "container_plugin_builtin_protected",
                manifest.plugin_id,
            )
        self.plugin_directory.mkdir(parents=True, exist_ok=True)
        safe_id = manifest.plugin_id.replace(".", "_")
        target = self.plugin_directory / (
            f"{safe_id}-{manifest.version}-{manifest.package_sha256[:16]}.ssplugin"
        )
        self._InstalledPath_Validate(target)
        if not target.exists():
            temporary = self.plugin_directory / f".install-{uuid.uuid4().hex[:8]}.tmp"
            try:
                shutil.copyfile(source, temporary)
                if _FileSha256_Get(temporary) != manifest.package_sha256:
                    raise DecoderProfileError("container_plugin_copy_hash_mismatch")
                os.replace(temporary, target)
            finally:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)
        return self._Manifest_Read(target, require_installed=True)

    def Discover(self) -> ContainerPluginDiscovery:
        manifests: list[ContainerPluginPackageManifest] = []
        errors: dict[Path, str] = {}
        if not self.plugin_directory.is_dir():
            return ContainerPluginDiscovery((), MappingProxyType({}))
        for path in sorted(
            self.plugin_directory.glob("*.ssplugin"),
            key=lambda item: item.name.casefold(),
        ):
            try:
                manifest = self._Manifest_Read(path, require_installed=True)
                if manifest.plugin_id in self.protected_plugin_ids:
                    raise DecoderProfileError(
                        "container_plugin_builtin_protected",
                        manifest.plugin_id,
                    )
                manifests.append(manifest)
            except DecoderProfileError as exc:
                errors[path] = str(exc)
        return ContainerPluginDiscovery(
            tuple(manifests),
            MappingProxyType(errors),
        )

    def Container_Load(
        self,
        manifest: ContainerPluginPackageManifest,
        trusted_factories: Mapping[str, Callable[[], LogContainerPlugin]],
    ) -> LogContainerPlugin:
        self._InstalledPath_Validate(manifest.source_path)
        if _FileSha256_Get(manifest.source_path) != manifest.package_sha256:
            raise DecoderProfileError("container_plugin_installed_hash_mismatch")
        factory = trusted_factories.get(manifest.entry_point)
        if factory is None:
            raise DecoderProfileError(
                "container_plugin_factory_not_trusted",
                manifest.entry_point,
            )
        plugin = factory()
        metadata = plugin.metadata
        if (
            metadata.plugin_id != manifest.plugin_id
            or metadata.version != manifest.version
            or metadata.api_version != manifest.api_version
        ):
            raise DecoderProfileError(
                "container_plugin_manifest_metadata_mismatch",
                manifest.plugin_id,
            )
        return plugin

    def _Manifest_Read(
        self,
        path: Path,
        *,
        require_installed: bool,
    ) -> ContainerPluginPackageManifest:
        source = Path(path)
        if require_installed:
            self._InstalledPath_Validate(source)
        if source.suffix.casefold() != ".ssplugin":
            raise DecoderProfileError("container_plugin_package_extension_invalid")
        try:
            package_size = source.stat().st_size
            if package_size > 64 * 1024 * 1024:
                raise DecoderProfileError("container_plugin_package_too_large")
            package_bytes = source.read_bytes()
            with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as archive:
                infos = archive.infolist()
                if len(infos) > 256:
                    raise DecoderProfileError("container_plugin_file_count_exceeded")
                seen_names: set[str] = set()
                manifest_info: zipfile.ZipInfo | None = None
                total_size = 0
                for info in infos:
                    name = _PluginMemberName_Validate(info.filename)
                    folded_name = name.casefold()
                    if folded_name in seen_names:
                        raise DecoderProfileError(
                            "container_plugin_duplicate_member",
                            name,
                        )
                    seen_names.add(folded_name)
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise DecoderProfileError(
                            "container_plugin_symlink_forbidden",
                            name,
                        )
                    if info.flag_bits & 0x1:
                        raise DecoderProfileError(
                            "container_plugin_encrypted_member",
                            name,
                        )
                    if info.file_size > 16 * 1024 * 1024:
                        raise DecoderProfileError(
                            "container_plugin_member_too_large",
                            name,
                        )
                    total_size += info.file_size
                    if total_size > 64 * 1024 * 1024:
                        raise DecoderProfileError(
                            "container_plugin_total_size_exceeded"
                        )
                    if name == "manifest.json":
                        manifest_info = info
                if manifest_info is None or manifest_info.file_size > 1024 * 1024:
                    raise DecoderProfileError(
                        "container_plugin_manifest_missing_or_too_large"
                    )
                manifest_document = _ManifestJson_Load(archive.read(manifest_info))
        except DecoderProfileError:
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise DecoderProfileError("container_plugin_package_invalid", str(exc)) from exc

        if manifest_document.get("format") != "SilverStar.ssplugin":
            raise DecoderProfileError("container_plugin_format_invalid")
        if manifest_document.get("plugin_type") not in (
            "log_container",
            "flight_log_container",
        ):
            raise DecoderProfileError("container_plugin_type_invalid")
        plugin_id = manifest_document.get("plugin_id")
        version = manifest_document.get("version")
        api_version = manifest_document.get("api_version")
        entry_point = manifest_document.get("entry_point")
        if (
            not isinstance(plugin_id, str)
            or len(plugin_id) > 128
            or not _PLUGIN_ID_PATTERN.fullmatch(plugin_id)
        ):
            raise DecoderProfileError("container_plugin_id_invalid")
        if (
            not isinstance(version, str)
            or len(version) > 64
            or not _PLUGIN_VERSION_PATTERN.fullmatch(version)
        ):
            raise DecoderProfileError("container_plugin_version_invalid")
        if (
            isinstance(api_version, bool)
            or not isinstance(api_version, int)
            or api_version != self.api_version
        ):
            raise DecoderProfileError(
                "container_plugin_api_incompatible",
                str(api_version),
            )
        if (
            not isinstance(entry_point, str)
            or len(entry_point) > 256
            or not _ENTRY_POINT_PATTERN.fullmatch(entry_point)
        ):
            raise DecoderProfileError("container_plugin_entry_point_invalid")
        return ContainerPluginPackageManifest(
            source_path=source,
            plugin_id=plugin_id,
            version=version,
            api_version=api_version,
            entry_point=entry_point,
            package_sha256=hashlib.sha256(package_bytes).hexdigest(),
            raw_manifest=MappingProxyType(dict(manifest_document)),
        )

    def _InstalledPath_Validate(self, path: Path) -> None:
        root = self.plugin_directory.resolve()
        candidate = Path(path).resolve()
        if candidate != root and root not in candidate.parents:
            raise DecoderProfileError("container_plugin_path_outside_directory")


def _PluginMemberName_Validate(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise DecoderProfileError("container_plugin_member_path_invalid", repr(name))
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or len(path.parts) > 12
        or any(part in ("", ".", "..") for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise DecoderProfileError("container_plugin_member_path_invalid", name)
    return path.as_posix()


def _ManifestJson_Load(source: bytes) -> Mapping[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DecoderProfileError(
                    "container_plugin_manifest_duplicate_key",
                    key,
                )
            result[key] = value
        return result

    try:
        document = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                DecoderProfileError(
                    "container_plugin_manifest_constant_invalid",
                    value,
                )
            ),
        )
    except DecoderProfileError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecoderProfileError("container_plugin_manifest_invalid", str(exc)) from exc
    if not isinstance(document, Mapping):
        raise DecoderProfileError("container_plugin_manifest_root_invalid")
    return document


def _FileSha256_Get(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
