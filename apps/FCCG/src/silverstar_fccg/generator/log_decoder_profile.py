from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import zipfile
from dataclasses import dataclass
from typing import Any

from silverstar_fccg.project.model import LogDecoderProfileReference
from silverstar_fccg.project.record_catalog import RecordCatalog_Validate

LOG_DECODER_PACKAGE_SCHEMA_ID = "silverstar.ssdecoder.package-schema/1.2"
LOG_DECODER_PACKAGE_SCHEMA_MAJOR = 1
LOG_DECODER_PACKAGE_SCHEMA_MINOR = 2
LOG_DECODER_PACKAGE_SCHEMA_VERSION = "1.2"
LOG_DECODER_CONTAINER_PLUGIN_ID = "silverstar.sslog.container/0.0"
LOG_DECODER_REQUIRED_FLP_VERSION = "0.1.0"
LOG_DECODER_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
LOG_DECODER_FALLBACK_CREATION_TIME = "1970-01-01T00:00:00+00:00"
LOG_DECODER_FORBIDDEN_SUFFIXES = frozenset(
    {
        ".bat",
        ".cmd",
        ".com",
        ".dll",
        ".exe",
        ".js",
        ".msi",
        ".ps1",
        ".py",
        ".pyd",
        ".pyc",
        ".sh",
        ".so",
        ".vbs",
    }
)


@dataclass(frozen=True, slots=True)
class LogDecoderPackageContext:
    project_name: str
    firmware_version: str
    firmware_commit: str
    fccg_version: str
    selected_log_format_profile: str
    container_plugin_id: str
    container_version: str
    creation_time_utc: str
    project_generation_fingerprint: str
    supported_primitive_types: tuple[str, ...]
    selected_protocols: dict[str, dict[str, str] | None]
    firmware_components: dict[str, str]
    hardware_identity: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LogDecoderPackageResult:
    relative_path: str
    content: bytes
    record_catalog_sha256: str
    project_semantics_sha256: str
    generation_profile_sha256: str
    package_sha256: str
    container_format_major: int
    container_format_minor: int
    record_catalog_content: bytes
    project_semantics_content: bytes
    container_plugin_id: str

    def Reference_Get(self) -> LogDecoderProfileReference:
        return LogDecoderProfileReference(
            relative_path=self.relative_path,
            package_schema=LOG_DECODER_PACKAGE_SCHEMA_VERSION,
            container_plugin_id=self.container_plugin_id,
            generation_profile_sha256=self.generation_profile_sha256,
            package_sha256=self.package_sha256,
        )


def _AlgorithmParameters_Validate(semantics: dict[str, Any]) -> None:
    sets = semantics.get("firmware_algorithm_parameters")
    if not isinstance(sets, list):
        raise ValueError("Missing firmware algorithm parameter sets")
    seen = set()
    lock_entries = semantics.get("component_locks")
    if not isinstance(lock_entries, list) or not all(
        isinstance(lock, dict) and isinstance(lock.get("component"), str)
        and isinstance(lock.get("manifest_sha256"), str) for lock in lock_entries
    ):
        raise ValueError("Invalid algorithm parameter schema locks")
    locks = {lock["component"]: lock["manifest_sha256"] for lock in lock_entries}
    if len(locks) != len(lock_entries) or any(
        len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
        for value in locks.values()
    ):
        raise ValueError("Invalid or duplicate algorithm parameter schema lock")
    for entry in sets:
        if not isinstance(entry, dict) or set(entry) != {"component", "schema_id", "manifest_sha256", "parameters"}:
            raise ValueError("Invalid firmware algorithm parameter set")
        component = entry["component"]
        if (not isinstance(component, str) or component in seen
                or component not in semantics["algorithms"] or component not in semantics["components"]
                or entry["schema_id"] != "silverstar.algorithm-parameters/1.0"
                or component not in locks
                or entry["manifest_sha256"] != locks.get(component)
                or not isinstance(entry["parameters"], list) or not entry["parameters"]):
            raise ValueError("Invalid algorithm parameter ownership/schema")
        seen.add(component)
        ids = set()
        for parameter in entry["parameters"]:
            if not isinstance(parameter, dict) or set(parameter) != {"id", "value", "unit", "representation", "storage_type", "description"}:
                raise ValueError("Invalid resolved algorithm parameter")
            for field in ("id", "unit", "description"):
                if not isinstance(parameter[field], str) or not parameter[field].strip():
                    raise ValueError("Invalid algorithm parameter identity/units")
            if parameter["id"] in ids or parameter["representation"] not in ("value", "sigma", "variance", "covariance_diagonal"):
                raise ValueError("Duplicate/invalid resolved algorithm parameter")
            ids.add(parameter["id"])
            value = parameter["value"]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Algorithm parameter value must be finite")
            if parameter["storage_type"] == "float32":
                try:
                    rounded = struct.unpack("<f", struct.pack("<f", value))[0]
                except (OverflowError, struct.error) as error:
                    raise ValueError("Unrepresentable float32 parameter") from error
                if rounded != value:
                    raise ValueError("Algorithm parameter is not resolved float32")
            elif parameter["storage_type"] != "int32" or type(value) is not int or not -(2**31) <= value < 2**31:
                raise ValueError("Invalid algorithm parameter storage type")


def CanonicalJson_Encode(value: Any) -> bytes:
    """Encode one stable UTF-8 JSON document with exactly one LF terminator."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def Sha256_Get(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def GenerationProfileHash_Get(
    record_catalog_sha256: str,
    project_semantics_sha256: str,
    container_plugin_id: str = LOG_DECODER_CONTAINER_PLUGIN_ID,
) -> str:
    """Apply the firmware-owned decoder-profile hash contract exactly."""
    return Sha256_Get(
        LOG_DECODER_PACKAGE_SCHEMA_ID.encode("utf-8")
        + b"\n"
        + container_plugin_id.encode("utf-8")
        + b"\n"
        + bytes.fromhex(record_catalog_sha256)
        + bytes.fromhex(project_semantics_sha256)
    )


def LogDecoderPackage_Build(
    record_catalog: dict[str, Any],
    project_semantics: dict[str, Any],
    context: LogDecoderPackageContext,
) -> LogDecoderPackageResult:
    record_catalog_bytes = CanonicalJson_Encode(record_catalog)
    project_semantics_bytes = CanonicalJson_Encode(project_semantics)
    record_catalog_sha256 = Sha256_Get(record_catalog_bytes)
    project_semantics_sha256 = Sha256_Get(project_semantics_bytes)
    generation_profile_sha256 = GenerationProfileHash_Get(
        record_catalog_sha256,
        project_semantics_sha256,
        context.container_plugin_id,
    )
    container_format_major, container_format_minor = _VersionPair_Parse(
        context.container_version
    )
    manifest = {
        "contains_executable_code": False,
        "container_plugin": {
            "id": context.container_plugin_id,
            "version_range": {
                "maximum_inclusive": context.container_version,
                "minimum_inclusive": context.container_version,
            },
        },
        "created_at_utc": (
            context.creation_time_utc
            or LOG_DECODER_FALLBACK_CREATION_TIME
        ),
        "entries": [
            "README.md",
            "checksums.sha256",
            "manifest.json",
            "project_semantics.json",
            "record_catalog.json",
        ],
        "fccg_version": context.fccg_version,
        "firmware_commit": context.firmware_commit,
        "firmware_version": context.firmware_version,
        "format": "SilverStar.ssdecoder",
        "generation_profile_sha256": generation_profile_sha256,
        "package_schema": {
            "id": LOG_DECODER_PACKAGE_SCHEMA_ID,
            "major": LOG_DECODER_PACKAGE_SCHEMA_MAJOR,
            "minor": LOG_DECODER_PACKAGE_SCHEMA_MINOR,
        },
        "project_name": context.project_name,
        "project_generation_fingerprint": (
            context.project_generation_fingerprint
        ),
        "protocols": context.selected_protocols,
        "firmware_components": context.firmware_components,
        "hardware": context.hardware_identity,
        "project_semantics_sha256": project_semantics_sha256,
        "record_catalog_sha256": record_catalog_sha256,
        "required_flp_minimum_version": LOG_DECODER_REQUIRED_FLP_VERSION,
        "selected_log_format_profile": context.selected_log_format_profile,
        "supported_primitive_types": list(context.supported_primitive_types),
    }
    readme = (
        "# SilverStar log decoder profile\n\n"
        "This archive is a deterministic, declarative configuration package for "
        "a generic SilverStar_FLP decoder. It contains no executable code and does "
        "not modify SilverStar_FLP.\n\n"
        "`record_catalog.json` describes the Flight Log container and record wire "
        "schema. `project_semantics.json` binds those records to this generated "
        "project's devices, capability routes, flight configuration, and logging "
        "policy. `project_semantics.algorithms` is the set of algorithms present "
        "onboard; it is not a whitelist for future offline replay in SilverStar_FLP. "
        "`CALIBRATION_RESULT` is the active correction snapshot, including a valid "
        "NONE/identity snapshot when no sampling procedure is selected. Verify "
        "`checksums.sha256` before loading the package.\n"
        "Firmware algorithm parameters are actual float32/int32 values with units "
        "and representation. Recorded Configuration is separate from Offline What-if. "
        "Package and semantics schemas are 1.2; 1.1 is unsupported.\n"
    ).encode("utf-8")
    payloads = {
        "README.md": readme,
        "manifest.json": CanonicalJson_Encode(manifest),
        "project_semantics.json": project_semantics_bytes,
        "record_catalog.json": record_catalog_bytes,
    }
    checksums = "".join(
        f"{Sha256_Get(content)}  {name}\n"
        for name, content in sorted(payloads.items())
    ).encode("ascii")
    payloads["checksums.sha256"] = checksums
    _LogDecoderEntries_Validate(tuple(payloads))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=LOG_DECODER_FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    package = buffer.getvalue()
    LogDecoderPackage_Verify(package)
    return LogDecoderPackageResult(
        relative_path=f"{context.project_name}.ssdecoder",
        content=package,
        record_catalog_sha256=record_catalog_sha256,
        project_semantics_sha256=project_semantics_sha256,
        generation_profile_sha256=generation_profile_sha256,
        package_sha256=Sha256_Get(package),
        container_format_major=container_format_major,
        container_format_minor=container_format_minor,
        record_catalog_content=record_catalog_bytes,
        project_semantics_content=project_semantics_bytes,
        container_plugin_id=context.container_plugin_id,
    )


def LogDecoderProfileHeader_Render(
    _reference: LogDecoderProfileReference,
) -> str:
    return """#ifndef __PROJECT_LOG_DECODER_PROFILE_H
#define __PROJECT_LOG_DECODER_PROFILE_H

/* AUTO-GENERATED BY SILVERSTAR_FCCG. DO NOT EDIT; THIS FILE MAY BE OVERWRITTEN. */

#include <stdint.h>

#define PROJECT_LOG_DECODER_HASH_SIZE 16U

typedef struct
{
    uint16_t package_schema_major;
    uint16_t package_schema_minor;
    uint16_t container_format_major;
    uint16_t container_format_minor;
    uint8_t record_catalog_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
    uint8_t project_semantics_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
    uint8_t generation_profile_hash_128[PROJECT_LOG_DECODER_HASH_SIZE];
} ProjectLogDecoderProfile;

void ProjectLogDecoderProfile_Get(ProjectLogDecoderProfile *profile);

#endif /* __PROJECT_LOG_DECODER_PROFILE_H */
"""


def LogDecoderProfileSource_Render(result: LogDecoderPackageResult) -> str:
    record_catalog = _DigestPrefixInitializer_Get(
        result.record_catalog_sha256
    )
    project_semantics = _DigestPrefixInitializer_Get(
        result.project_semantics_sha256
    )
    generation_profile = _DigestPrefixInitializer_Get(
        result.generation_profile_sha256
    )
    return f"""#include \"project_log_decoder_profile.h\"

/* AUTO-GENERATED BY SILVERSTAR_FCCG. DO NOT EDIT; THIS FILE MAY BE OVERWRITTEN. */

#include <string.h>

#include \"silverstar_assert.h\"

static const uint8_t s_record_catalog_hash[PROJECT_LOG_DECODER_HASH_SIZE] =
{{
    {record_catalog}
}};
static const uint8_t s_project_semantics_hash[PROJECT_LOG_DECODER_HASH_SIZE] =
{{
    {project_semantics}
}};
static const uint8_t s_generation_profile_hash[PROJECT_LOG_DECODER_HASH_SIZE] =
{{
    {generation_profile}
}};

void ProjectLogDecoderProfile_Get(ProjectLogDecoderProfile *profile)
{{
    SILVERSTAR_ASSERT_OBJECT(profile, ProjectLogDecoderProfile,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    (void)memset(profile, 0, sizeof(*profile));
    profile->package_schema_major = {LOG_DECODER_PACKAGE_SCHEMA_MAJOR}U;
    profile->package_schema_minor = {LOG_DECODER_PACKAGE_SCHEMA_MINOR}U;
    profile->container_format_major = {result.container_format_major}U;
    profile->container_format_minor = {result.container_format_minor}U;
    (void)memcpy(profile->record_catalog_hash_128,
        s_record_catalog_hash, sizeof(profile->record_catalog_hash_128));
    (void)memcpy(profile->project_semantics_hash_128,
        s_project_semantics_hash, sizeof(profile->project_semantics_hash_128));
    (void)memcpy(profile->generation_profile_hash_128,
        s_generation_profile_hash, sizeof(profile->generation_profile_hash_128));
}}
"""


def _DigestPrefixInitializer_Get(digest: str) -> str:
    raw = bytes.fromhex(digest)
    if len(raw) != 32:
        raise ValueError("SHA-256 digest must contain exactly 32 bytes")
    values = [f"0x{value:02X}U" for value in raw[:16]]
    return ",\n    ".join(
        ", ".join(values[index : index + 8])
        for index in range(0, len(values), 8)
    )


def _VersionPair_Parse(value: str) -> tuple[int, int]:
    parts = value.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
        raise ValueError(f"Container format version is invalid: {value!r}")
    major, minor = (int(part) for part in parts[:2])
    if any(version < 0 or version > 0xFFFF for version in (major, minor)):
        raise ValueError(f"Container format version is out of range: {value!r}")
    return major, minor


def _LogDecoderEntries_Validate(names: tuple[str, ...]) -> None:
    for name in names:
        normalized = name.casefold()
        if (
            not name
            or "\\" in name
            or name.startswith("/")
            or any(part in ("", ".", "..") for part in name.split("/"))
            or any(normalized.endswith(suffix) for suffix in LOG_DECODER_FORBIDDEN_SUFFIXES)
        ):
            raise ValueError(f"Unsafe log decoder package entry: {name!r}")


def LogDecoderPackage_Verify(content: bytes) -> dict[str, Any]:
    """Verify the complete deterministic, data-only decoder-profile contract."""
    required_entries = (
        "README.md",
        "checksums.sha256",
        "manifest.json",
        "project_semantics.json",
        "record_catalog.json",
    )
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            names = tuple(archive.namelist())
            _LogDecoderEntries_Validate(names)
            if names != required_entries or len(names) != len(set(names)):
                raise ValueError(
                    "Log decoder package entries are missing, duplicated, or unordered"
                )
            payloads = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("Log decoder package is not a valid ZIP archive") from error

    json_values: dict[str, Any] = {}
    for name in (
        "manifest.json",
        "project_semantics.json",
        "record_catalog.json",
    ):
        raw = payloads[name]
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Log decoder package JSON is invalid: {name}") from error
        if CanonicalJson_Encode(value) != raw:
            raise ValueError(f"Log decoder package JSON is not canonical: {name}")
        json_values[name] = value

    manifest = json_values["manifest.json"]
    if not isinstance(manifest, dict):
        raise ValueError("Log decoder manifest must be an object")
    package_schema = manifest.get("package_schema")
    container_plugin = manifest.get("container_plugin")
    if (
        manifest.get("contains_executable_code") is not False
        or manifest.get("entries") != list(required_entries)
        or package_schema
        != {
            "id": LOG_DECODER_PACKAGE_SCHEMA_ID,
            "major": LOG_DECODER_PACKAGE_SCHEMA_MAJOR,
            "minor": LOG_DECODER_PACKAGE_SCHEMA_MINOR,
        }
        or not isinstance(container_plugin, dict)
        or not isinstance(container_plugin.get("id"), str)
        or not container_plugin["id"]
    ):
        raise ValueError("Log decoder manifest contract is invalid")
    protocols = manifest.get("protocols")
    if (
        not isinstance(protocols, dict)
        or set(protocols) != {"telemetry", "maintenance", "logging"}
    ):
        raise ValueError("Log decoder manifest protocol locks are incomplete")
    for category, selection in protocols.items():
        if selection is None:
            if category == "logging":
                raise ValueError(
                    "Log decoder manifest requires a Logging Protocol lock"
                )
            continue
        if (
            not isinstance(selection, dict)
            or set(selection)
            != {"component", "version", "profile", "manifest_sha256"}
            or not all(
                isinstance(selection[field], str) and bool(selection[field])
                for field in ("component", "version", "profile")
            )
            or not isinstance(selection["manifest_sha256"], str)
            or len(selection["manifest_sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in selection["manifest_sha256"]
            )
        ):
            raise ValueError(
                f"Log decoder manifest protocol lock is invalid: {category}"
            )
    semantics = json_values["project_semantics.json"]
    required_semantics = {
        "schema_id",
        "project",
        "protocols",
        "components",
        "algorithms",
        "firmware_algorithm_parameters",
        "hardware",
        "devices",
        "resource_assignments",
        "strategies",
        "modes",
        "logging_streams",
    }
    if (
        not isinstance(semantics, dict)
        or semantics.get("schema_id") != "silverstar.project-semantics/1.2"
        or not required_semantics.issubset(semantics)
        or semantics.get("protocols") != protocols
        or not isinstance(semantics.get("components"), list)
        or not isinstance(semantics.get("algorithms"), list)
        or not isinstance(semantics.get("hardware"), dict)
        or not isinstance(semantics.get("devices"), list)
        or not isinstance(semantics.get("resource_assignments"), list)
        or not isinstance(semantics.get("logging_streams"), list)
    ):
        raise ValueError("Log decoder project semantics contract is invalid")
    if (
        not isinstance(manifest.get("firmware_components"), dict)
        or not isinstance(manifest.get("hardware"), dict)
        or manifest.get("selected_log_format_profile")
        != protocols["logging"]["profile"]
    ):
        raise ValueError("Log decoder firmware identity contract is invalid")
    _AlgorithmParameters_Validate(semantics)
    RecordCatalog_Validate(
        json_values["record_catalog.json"], "decoder Record Catalog"
    )

    checksums: dict[str, str] = {}
    try:
        checksum_lines = payloads["checksums.sha256"].decode("ascii").splitlines()
    except UnicodeError as error:
        raise ValueError("Log decoder checksums are not ASCII") from error
    for line in checksum_lines:
        parts = line.split("  ", 1)
        if (
            len(parts) != 2
            or len(parts[0]) != 64
            or any(character not in "0123456789abcdef" for character in parts[0])
            or parts[1] in checksums
        ):
            raise ValueError("Log decoder checksum catalog is invalid")
        checksums[parts[1]] = parts[0]
    checksummed_entries = set(required_entries) - {"checksums.sha256"}
    if set(checksums) != checksummed_entries:
        raise ValueError("Log decoder checksum coverage is incomplete")
    if any(
        Sha256_Get(payloads[name]) != digest
        for name, digest in checksums.items()
    ):
        raise ValueError("Log decoder checksum verification failed")

    record_catalog_sha256 = Sha256_Get(payloads["record_catalog.json"])
    project_semantics_sha256 = Sha256_Get(payloads["project_semantics.json"])
    generation_profile_sha256 = GenerationProfileHash_Get(
        record_catalog_sha256,
        project_semantics_sha256,
        str(container_plugin["id"]),
    )
    if (
        manifest.get("record_catalog_sha256") != record_catalog_sha256
        or manifest.get("project_semantics_sha256")
        != project_semantics_sha256
        or manifest.get("generation_profile_sha256")
        != generation_profile_sha256
    ):
        raise ValueError("Log decoder manifest hashes are inconsistent")
    return manifest
