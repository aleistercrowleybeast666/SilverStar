from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from silverstar_flp.app.version import __version__
from silverstar_flp.decoder_profiles.catalog import (
    SUPPORTED_SCALAR_TYPES,
    RecordCatalog,
)
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.semantics import ProjectSemantics
from silverstar_flp.plugins.api.log_container import LogContainerPlugin

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_HASH128_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_CHECKSUM_LINE_PATTERN = re.compile(r"^([0-9a-fA-F]{64})[ \t]+[* ]?(.+)$")
_FORBIDDEN_SUFFIXES = frozenset(
    {
        ".app",
        ".bat",
        ".cmd",
        ".com",
        ".dll",
        ".dylib",
        ".exe",
        ".jar",
        ".js",
        ".lnk",
        ".msi",
        ".pif",
        ".ps1",
        ".py",
        ".pyc",
        ".pyd",
        ".scr",
        ".sh",
        ".so",
        ".vbs",
    }
)
_REQUIRED_FILES = frozenset(
    {
        "manifest.json",
        "record_catalog.json",
        "project_semantics.json",
        "checksums.sha256",
        "README.md",
    }
)
_BUILTIN_CONTAINER_PLUGIN_ID = "silverstar.flight_log.container.0_0"
_CONTAINER_PLUGIN_ID_ALIASES = MappingProxyType(
    {
        # Firmware/FCCG schema spelling for the same SSLOG0 0.0 wire container.
        "silverstar.sslog.container/0.0": _BUILTIN_CONTAINER_PLUGIN_ID,
    }
)


@dataclass(frozen=True, slots=True)
class DecoderPackageLimits:
    maximum_archive_bytes: int = 64 * 1024 * 1024
    maximum_total_uncompressed_bytes: int = 64 * 1024 * 1024
    maximum_member_bytes: int = 16 * 1024 * 1024
    maximum_file_count: int = 128
    maximum_path_depth: int = 8
    maximum_compression_ratio: float = 500.0
    maximum_json_depth: int = 64
    maximum_json_nodes: int = 200_000


@dataclass(frozen=True, slots=True)
class DecoderProfilePackage:
    source_path: Path
    manifest: Mapping[str, Any]
    catalog: RecordCatalog
    semantics: ProjectSemantics
    package_sha256: str
    generation_profile_sha256: str
    generation_profile_hash_128: str
    record_catalog_hash_128: str
    project_semantics_hash_128: str
    required_container_plugin_id: str
    declared_container_plugin_id: str
    required_container_version_range: str
    required_container_api_version: int
    package_schema_major: int
    package_schema_minor: int
    checksums: Mapping[str, str]
    member_names: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def Load(
        cls,
        path: Path,
        *,
        limits: DecoderPackageLimits | None = None,
        container_plugins: Mapping[str, LogContainerPlugin] | None = None,
    ) -> DecoderProfilePackage:
        source_path = Path(path)
        package_limits = limits or DecoderPackageLimits()
        try:
            archive_size = source_path.stat().st_size
        except OSError as exc:
            raise DecoderProfileError("decoder_package_open_failed", str(exc)) from exc
        if archive_size > package_limits.maximum_archive_bytes:
            raise DecoderProfileError(
                "decoder_package_archive_too_large",
                f"actual={archive_size}:maximum={package_limits.maximum_archive_bytes}",
            )
        try:
            archive_bytes = source_path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
                members = _ArchiveMembers_Validate(archive, package_limits)
                files = {name: archive.read(info) for name, info in members.items()}
        except DecoderProfileError:
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise DecoderProfileError("decoder_package_zip_invalid", str(exc)) from exc

        actual_names = frozenset(files)
        if actual_names != _REQUIRED_FILES:
            missing = sorted(_REQUIRED_FILES - actual_names)
            unexpected = sorted(actual_names - _REQUIRED_FILES)
            raise DecoderProfileError(
                (
                    "decoder_package_required_file_missing"
                    if missing
                    else "decoder_package_unexpected_member"
                ),
                ",".join(missing or unexpected),
            )
        catalog_name = "record_catalog.json"
        semantics_name = "project_semantics.json"
        checksums = _Checksums_Parse(files["checksums.sha256"])
        _Checksums_Validate(files, checksums)

        manifest = _Json_Load(files["manifest.json"], "manifest.json", package_limits)
        catalog_document = _Json_Load(files[catalog_name], catalog_name, package_limits)
        semantics_document = _Json_Load(
            files[semantics_name],
            semantics_name,
            package_limits,
        )
        _CanonicalJson_Validate(
            manifest,
            files["manifest.json"],
            "manifest.json",
        )
        _CanonicalJson_Validate(
            catalog_document,
            files[catalog_name],
            catalog_name,
        )
        _CanonicalJson_Validate(
            semantics_document,
            files[semantics_name],
            semantics_name,
        )
        _Manifest_Validate(manifest, actual_names)
        _ApplicationVersion_Validate(manifest)
        _PrimitiveTypes_Validate(manifest)
        try:
            files["README.md"].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecoderProfileError("decoder_package_readme_not_utf8") from exc

        catalog = RecordCatalog.FromDocument(
            catalog_document,
            source_bytes=files[catalog_name],
        )
        semantics = ProjectSemantics.FromDocument(
            semantics_document,
            source_bytes=files[semantics_name],
            manifest=manifest,
        )
        from silverstar_flp.decoder_profiles.algorithm_parameters import (
            FirmwareParameters_CheckPlugins,
        )

        replay_declaration = semantics_document.get("metadata_declarations", {}).get(
            "navigation_replay", {}
        )
        integrity_revision = replay_declaration.get("gnss_integrity_revision", 0)
        if type(integrity_revision) is not int or integrity_revision not in (0, 2, 3):
            raise DecoderProfileError("gnss_integrity_revision_unsupported")
        FirmwareParameters_CheckPlugins(
            semantics_document["firmware_algorithm_parameters"],
            integrity_revision=integrity_revision,
        )
        semantics = semantics.Catalog_Bind(catalog)
        _CatalogSemantics_Validate(catalog, semantics)
        if not 1 <= catalog.schema_version <= 1:
            raise DecoderProfileError(
                "decoder_record_catalog_schema_unsupported",
                str(catalog.schema_version),
            )
        if semantics.schema_version != (1 << 16) | 2:
            raise DecoderProfileError(
                "decoder_project_semantics_schema_unsupported",
                str(semantics.schema_version),
            )

        (
            declared_container_plugin_id,
            container_version_range,
            container_api_version,
        ) = _ContainerRequirement_Parse(
            manifest,
        )
        container_plugin_id = ContainerPluginId_Normalize(declared_container_plugin_id)
        package_schema_major, package_schema_minor = _PackageSchema_Get(manifest)
        package_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        catalog_hash_128 = catalog.sha256[:32]
        semantics_hash_128 = semantics.sha256[:32]
        _DeclaredHash_Validate(
            manifest,
            ("record_catalog_sha256",),
            catalog.sha256,
            "decoder_record_catalog_hash_mismatch",
            required=True,
        )
        _DeclaredHash_Validate(
            manifest,
            ("record_catalog_hash_128",),
            catalog_hash_128,
            "decoder_record_catalog_hash_mismatch",
        )
        _DeclaredHash_Validate(
            manifest,
            ("project_semantics_sha256",),
            semantics.sha256,
            "decoder_project_semantics_hash_mismatch",
            required=True,
        )
        _DeclaredHash_Validate(
            manifest,
            ("project_semantics_hash_128",),
            semantics_hash_128,
            "decoder_project_semantics_hash_mismatch",
        )
        declared_generation_sha256 = _Hash_Get(
            manifest,
            ("generation_profile_sha256",),
            length=64,
        )
        if declared_generation_sha256 is None:
            raise DecoderProfileError("decoder_generation_profile_hash_missing")
        generation_sha256 = declared_generation_sha256
        _GenerationHash_Validate(
            manifest,
            declared_container_plugin_id,
            catalog.sha256,
            semantics.sha256,
            generation_sha256,
        )
        declared_generation_hash_128 = _Hash_Get(
            manifest,
            ("generation_profile_hash_128",),
            length=32,
        )
        if (
            declared_generation_hash_128 is not None
            and declared_generation_hash_128 != generation_sha256[:32]
        ):
            raise DecoderProfileError("decoder_generation_profile_hash_mismatch")
        generation_hash_128 = declared_generation_hash_128 or generation_sha256[:32]

        result = cls(
            source_path=source_path,
            manifest=MappingProxyType(dict(manifest)),
            catalog=catalog,
            semantics=semantics,
            package_sha256=package_sha256,
            generation_profile_sha256=generation_sha256,
            generation_profile_hash_128=generation_hash_128,
            record_catalog_hash_128=catalog_hash_128,
            project_semantics_hash_128=semantics_hash_128,
            required_container_plugin_id=container_plugin_id,
            declared_container_plugin_id=declared_container_plugin_id,
            required_container_version_range=container_version_range,
            required_container_api_version=container_api_version,
            package_schema_major=package_schema_major,
            package_schema_minor=package_schema_minor,
            checksums=MappingProxyType(dict(checksums)),
            member_names=tuple(sorted(actual_names)),
            metadata=MappingProxyType(
                {
                    "catalog_member": catalog_name,
                    "semantics_member": semantics_name,
                    "strict_layout": True,
                    "declared_container_plugin_id": declared_container_plugin_id,
                }
            ),
        )
        if container_plugins is not None:
            plugin = container_plugins.get(declared_container_plugin_id) or container_plugins.get(
                container_plugin_id
            )
            if plugin is None:
                raise DecoderProfileError(
                    "decoder_container_plugin_missing",
                    container_plugin_id,
                )
            result.Container_Validate(plugin)
        return result

    def Container_Validate(self, plugin: LogContainerPlugin) -> None:
        metadata = plugin.metadata
        if (
            ContainerPluginId_Normalize(metadata.plugin_id)
            != self.required_container_plugin_id
        ):
            raise DecoderProfileError(
                "decoder_container_plugin_mismatch",
                f"required={self.required_container_plugin_id}:actual={metadata.plugin_id}",
            )
        if metadata.api_version != self.required_container_api_version:
            raise DecoderProfileError(
                "decoder_container_api_incompatible",
                f"required={self.required_container_api_version}:actual={metadata.api_version}",
            )
        if not ContainerVersion_IsCompatible(
            metadata.version,
            self.required_container_version_range,
        ):
            raise DecoderProfileError(
                "decoder_container_version_incompatible",
                (
                    f"required={self.required_container_version_range}:"
                    f"actual={metadata.version}"
                ),
            )


def ContainerPluginId_Normalize(plugin_id: str) -> str:
    """Resolve only audited aliases for an identical trusted wire container."""
    return _CONTAINER_PLUGIN_ID_ALIASES.get(plugin_id, plugin_id)


def _ArchiveMembers_Validate(
    archive: zipfile.ZipFile,
    limits: DecoderPackageLimits,
) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > limits.maximum_file_count:
        raise DecoderProfileError(
            "decoder_package_file_count_exceeded",
            str(len(entries)),
        )
    members: dict[str, zipfile.ZipInfo] = {}
    seen_names: set[str] = set()
    total_size = 0
    for info in entries:
        name = _MemberName_Normalize(info.filename, limits.maximum_path_depth)
        folded_name = name.casefold()
        if folded_name in seen_names:
            raise DecoderProfileError("decoder_package_duplicate_member", name)
        seen_names.add(folded_name)
        if info.flag_bits & 0x1:
            raise DecoderProfileError("decoder_package_encrypted_member", name)
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode):
            raise DecoderProfileError("decoder_package_symlink_forbidden", name)
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise DecoderProfileError("decoder_package_special_file_forbidden", name)
        if info.is_dir():
            continue
        if PurePosixPath(name).suffix.casefold() in _FORBIDDEN_SUFFIXES:
            raise DecoderProfileError("decoder_package_executable_forbidden", name)
        if info.file_size > limits.maximum_member_bytes:
            raise DecoderProfileError("decoder_package_member_too_large", name)
        if info.compress_size == 0 and info.file_size:
            raise DecoderProfileError("decoder_package_compression_ratio_exceeded", name)
        if info.compress_size:
            ratio = info.file_size / info.compress_size
            if ratio > limits.maximum_compression_ratio:
                raise DecoderProfileError(
                    "decoder_package_compression_ratio_exceeded",
                    f"{name}:{ratio:.1f}",
                )
        total_size += info.file_size
        if total_size > limits.maximum_total_uncompressed_bytes:
            raise DecoderProfileError("decoder_package_total_size_exceeded")
        members[name] = info
    return members


def _MemberName_Normalize(name: str, maximum_depth: int) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise DecoderProfileError("decoder_package_member_path_invalid", repr(name))
    path = PurePosixPath(name)
    if path.is_absolute() or len(path.parts) > maximum_depth:
        raise DecoderProfileError("decoder_package_member_path_invalid", name)
    if any(part in ("", ".", "..") for part in path.parts):
        raise DecoderProfileError("decoder_package_member_path_invalid", name)
    if path.parts and ":" in path.parts[0]:
        raise DecoderProfileError("decoder_package_member_path_invalid", name)
    return path.as_posix()


def _Json_Load(
    source: bytes,
    name: str,
    limits: DecoderPackageLimits,
) -> Mapping[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DecoderProfileError(
                    "decoder_package_json_duplicate_key",
                    f"{name}:{key}",
                )
            result[key] = value
        return result

    def constant_reject(value: str) -> None:
        raise DecoderProfileError("decoder_package_json_constant_invalid", f"{name}:{value}")

    try:
        decoded = source.decode("utf-8")
        document = json.loads(
            decoded,
            object_pairs_hook=object_pairs,
            parse_constant=constant_reject,
        )
    except DecoderProfileError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecoderProfileError("decoder_package_json_invalid", f"{name}:{exc}") from exc
    if not isinstance(document, Mapping):
        raise DecoderProfileError("decoder_package_json_root_invalid", name)
    _JsonLimits_Validate(document, limits)
    return document


def _JsonLimits_Validate(document: Any, limits: DecoderPackageLimits) -> None:
    pending: list[tuple[Any, int]] = [(document, 1)]
    node_count = 0
    while pending:
        value, depth = pending.pop()
        node_count += 1
        if node_count > limits.maximum_json_nodes:
            raise DecoderProfileError("decoder_package_json_nodes_exceeded")
        if depth > limits.maximum_json_depth:
            raise DecoderProfileError("decoder_package_json_depth_exceeded")
        if isinstance(value, Mapping):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)


def _CanonicalJson_Validate(
    document: Mapping[str, Any],
    source: bytes,
    name: str,
) -> None:
    canonical = (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if source != canonical:
        raise DecoderProfileError(
            "decoder_package_json_not_canonical",
            name,
        )


def _Manifest_Validate(
    manifest: Mapping[str, Any],
    actual_names: frozenset[str],
) -> None:
    if manifest.get("format") != "SilverStar.ssdecoder":
        raise DecoderProfileError("decoder_package_format_invalid")
    major, minor = _PackageSchema_Get(manifest)
    if major != 1 or minor != 2:
        raise DecoderProfileError(
            "decoder_package_format_version_unsupported",
            f"{major}.{minor}",
        )
    package_schema = manifest.get("package_schema")
    if isinstance(package_schema, Mapping):
        schema_id = package_schema.get("id")
        if schema_id != "silverstar.ssdecoder.package-schema/1.2":
            raise DecoderProfileError("decoder_package_schema_invalid")
    else:
        raise DecoderProfileError("decoder_package_schema_invalid")
    if manifest.get("contains_executable_code") is not False:
        raise DecoderProfileError("decoder_package_executable_declaration_invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise DecoderProfileError("decoder_package_manifest_entries_invalid")
    normalized = [_MemberName_Normalize(item, 64) for item in entries]
    if len({item.casefold() for item in normalized}) != len(normalized):
        raise DecoderProfileError("decoder_package_manifest_entry_duplicate")
    if frozenset(normalized) != actual_names:
        raise DecoderProfileError("decoder_package_manifest_entries_mismatch")


def _PackageSchema_Get(manifest: Mapping[str, Any]) -> tuple[int, int]:
    package_schema = manifest.get("package_schema")
    if not isinstance(package_schema, Mapping):
        raise DecoderProfileError("decoder_package_schema_invalid")
    major = package_schema.get("major")
    minor = package_schema.get("minor")
    if (
        isinstance(major, bool)
        or not isinstance(major, int)
        or isinstance(minor, bool)
        or not isinstance(minor, int)
        or major < 0
        or minor < 0
    ):
        raise DecoderProfileError("decoder_package_schema_invalid")
    return major, minor


def _ApplicationVersion_Validate(manifest: Mapping[str, Any]) -> None:
    required = manifest.get("required_flp_minimum_version")
    if not isinstance(required, str) or not required:
        raise DecoderProfileError("decoder_required_flp_version_invalid")
    if _Version_Parse(__version__) < _Version_Parse(required):
        raise DecoderProfileError(
            "decoder_required_flp_version_not_met",
            f"required={required}:actual={__version__}",
        )


def _PrimitiveTypes_Validate(manifest: Mapping[str, Any]) -> None:
    declared = manifest.get("supported_primitive_types")
    if not isinstance(declared, list) or not all(
        isinstance(item, str) for item in declared
    ):
        raise DecoderProfileError("decoder_primitive_types_invalid")
    unsupported = sorted(
        set(declared) - (set(SUPPORTED_SCALAR_TYPES) | {"pad", "padding"})
    )
    if unsupported:
        raise DecoderProfileError(
            "decoder_primitive_type_unsupported",
            ",".join(unsupported),
        )


def _CatalogSemantics_Validate(
    catalog: RecordCatalog,
    semantics: ProjectSemantics,
) -> None:
    layouts_by_name: dict[str, list[Any]] = {}
    for layout in catalog.layouts.values():
        layouts_by_name.setdefault(layout.name.upper(), []).append(layout)
    descriptor_context_fields = {
        "descriptor_id",
        "source_descriptor_id",
        "physical_device_id",
        "capability_class",
        "instance_id",
        "plugin_id",
        "model",
    }
    for record_name, record_semantics in semantics.records.items():
        layouts = layouts_by_name.get(record_name)
        if not layouts:
            raise DecoderProfileError(
                "decoder_semantics_record_unknown",
                record_name,
            )
        for layout in layouts:
            fields = {
                field.name: field
                for field in layout.fields
                if field.name is not None
            }
            for partition in record_semantics.partition_by:
                if partition not in fields and partition not in descriptor_context_fields:
                    raise DecoderProfileError(
                        "decoder_semantics_partition_field_unknown",
                        f"{record_name}:{partition}",
                    )
            for channel in record_semantics.channels:
                value_layout = fields.get(channel.value_field)
                if value_layout is None:
                    raise DecoderProfileError(
                        "decoder_semantics_value_field_unknown",
                        f"{record_name}:{channel.value_field}",
                    )
                if (
                    channel.timestamp_field is not None
                    and channel.timestamp_field not in fields
                ):
                    raise DecoderProfileError(
                        "decoder_semantics_timestamp_field_unknown",
                        f"{record_name}:{channel.timestamp_field}",
                    )
                if (
                    channel.validity_field is not None
                    and channel.validity_field != "__common_valid_flags__"
                    and channel.validity_field not in fields
                ):
                    raise DecoderProfileError(
                        "decoder_semantics_validity_field_unknown",
                        f"{record_name}:{channel.validity_field}",
                    )
                if channel.columns and len(channel.columns) != value_layout.count:
                    raise DecoderProfileError(
                        "decoder_semantics_columns_mismatch",
                        f"{record_name}:{channel.value_field}",
                    )


def _Checksums_Parse(source: bytes) -> dict[str, str]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecoderProfileError("decoder_package_checksums_not_utf8") from exc
    checksums: dict[str, str] = {}
    folded_names: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise DecoderProfileError(
                "decoder_package_checksum_line_invalid",
                str(line_number),
            )
        name = _MemberName_Normalize(match.group(2), 64)
        folded_name = name.casefold()
        if folded_name in folded_names:
            raise DecoderProfileError("decoder_package_checksum_duplicate", name)
        folded_names.add(folded_name)
        checksums[name] = match.group(1).lower()
    return checksums


def _Checksums_Validate(files: Mapping[str, bytes], checksums: Mapping[str, str]) -> None:
    expected_names = frozenset(name for name in files if name != "checksums.sha256")
    if frozenset(checksums) != expected_names:
        raise DecoderProfileError("decoder_package_checksum_entries_mismatch")
    for name, expected in checksums.items():
        actual = hashlib.sha256(files[name]).hexdigest()
        if actual != expected:
            raise DecoderProfileError(
                "decoder_package_checksum_mismatch",
                name,
            )


def _ContainerRequirement_Parse(
    manifest: Mapping[str, Any],
) -> tuple[str, str, int]:
    container = manifest.get("container_plugin")
    if not isinstance(container, Mapping):
        raise DecoderProfileError("decoder_container_plugin_requirement_invalid")
    plugin_id = container.get("id")
    version_range = container.get("version_range")
    api_version = container.get("api_version", 1)
    if not isinstance(plugin_id, str) or not plugin_id:
        raise DecoderProfileError("decoder_container_plugin_requirement_invalid")
    if not isinstance(version_range, Mapping):
        raise DecoderProfileError("decoder_container_version_requirement_invalid")
    minimum = version_range.get("minimum_inclusive")
    maximum = version_range.get("maximum_inclusive")
    if not isinstance(minimum, str) or not isinstance(maximum, str):
        raise DecoderProfileError("decoder_container_version_requirement_invalid")
    normalized_version_range = f">={minimum},<={maximum}"
    if isinstance(api_version, bool) or not isinstance(api_version, int) or api_version <= 0:
        raise DecoderProfileError("decoder_container_api_requirement_invalid")
    return plugin_id, normalized_version_range, api_version


def _Hash_Get(
    manifest: Mapping[str, Any],
    names: tuple[str, ...],
    *,
    length: int,
) -> str | None:
    for name in names:
        value = manifest.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise DecoderProfileError("decoder_package_hash_invalid", name)
        normalized = value.lower()
        pattern = _SHA256_PATTERN if length == 64 else _HASH128_PATTERN
        if pattern.fullmatch(normalized) is None:
            raise DecoderProfileError("decoder_package_hash_invalid", name)
        return normalized
    return None


def _DeclaredHash_Validate(
    manifest: Mapping[str, Any],
    names: tuple[str, ...],
    actual: str,
    error_code: str,
    *,
    required: bool = False,
) -> None:
    expected = _Hash_Get(manifest, names, length=len(actual))
    if expected is None and required:
        raise DecoderProfileError(error_code.replace("_mismatch", "_missing"))
    if expected is not None and expected != actual:
        raise DecoderProfileError(error_code)


def _GenerationHash_Validate(
    manifest: Mapping[str, Any],
    container_plugin_id: str,
    catalog_sha256: str,
    semantics_sha256: str,
    declared_sha256: str,
) -> None:
    package_schema = manifest.get("package_schema")
    if not isinstance(package_schema, Mapping):
        raise DecoderProfileError("decoder_package_schema_invalid")
    schema_id = package_schema.get("id")
    if not isinstance(schema_id, str) or not schema_id:
        raise DecoderProfileError("decoder_package_schema_invalid")
    binary_contract = hashlib.sha256(
        schema_id.encode("utf-8")
        + b"\n"
        + container_plugin_id.encode("utf-8")
        + b"\n"
        + bytes.fromhex(catalog_sha256)
        + bytes.fromhex(semantics_sha256)
    ).hexdigest()
    if declared_sha256 != binary_contract:
        raise DecoderProfileError(
            "decoder_generation_profile_hash_mismatch"
        )


def _Version_Parse(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+].*)?", version.strip())
    if match is None:
        raise DecoderProfileError("decoder_container_version_invalid", version)
    return tuple(int(value or 0) for value in match.groups())


def ContainerVersion_IsCompatible(actual_version: str, version_range: str) -> bool:
    actual = _Version_Parse(actual_version)
    requirement = version_range.strip()
    if requirement in ("", "*"):
        return True
    for alternative in requirement.split("||"):
        constraints = [item for item in re.split(r"[, ]+", alternative.strip()) if item]
        if constraints and all(_VersionConstraint_Matches(actual, item) for item in constraints):
            return True
    return False


def _VersionConstraint_Matches(actual: tuple[int, int, int], constraint: str) -> bool:
    if constraint.endswith(".*"):
        expected = _Version_Parse(constraint[:-2])
        components = constraint[:-2].lstrip("v").split(".")
        return actual[: len(components)] == expected[: len(components)]
    if constraint.startswith("^"):
        lower = _Version_Parse(constraint[1:])
        upper = (lower[0] + 1, 0, 0) if lower[0] else (0, lower[1] + 1, 0)
        return lower <= actual < upper
    if constraint.startswith("~"):
        lower = _Version_Parse(constraint[1:])
        upper = (lower[0], lower[1] + 1, 0)
        return lower <= actual < upper
    match = re.fullmatch(r"(>=|<=|>|<|==|=)?(.+)", constraint)
    if match is None:
        return False
    operator = match.group(1) or "=="
    expected = _Version_Parse(match.group(2))
    return {
        ">=": actual >= expected,
        "<=": actual <= expected,
        ">": actual > expected,
        "<": actual < expected,
        "==": actual == expected,
        "=": actual == expected,
    }[operator]
