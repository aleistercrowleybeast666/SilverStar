from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

_HASH128_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
DECODER_PROFILE_DESCRIPTOR_RECORD_TYPE = 0x1D
DECODER_PROFILE_DESCRIPTOR_RECORD_VERSION = 0
DECODER_PROFILE_DESCRIPTOR_PAYLOAD_SIZE = 64


@dataclass(frozen=True, slots=True)
class DecoderProfileDescriptor:
    package_schema_major: int
    package_schema_minor: int
    container_format_major: int
    container_format_minor: int
    record_catalog_hash_128: str
    project_semantics_hash_128: str
    generation_profile_hash_128: str

    @classmethod
    def FromPayload(
        cls,
        payload: Mapping[str, Any],
    ) -> DecoderProfileDescriptor:
        package_major, package_minor = _PackageSchema_Get(payload)
        container_major, container_minor = _ContainerVersion_Get(payload)
        return cls(
            package_schema_major=package_major,
            package_schema_minor=package_minor,
            container_format_major=container_major,
            container_format_minor=container_minor,
            record_catalog_hash_128=_Hash_Get(
                payload,
                "record_catalog_hash_128",
            ),
            project_semantics_hash_128=_Hash_Get(
                payload,
                "project_semantics_hash_128",
            ),
            generation_profile_hash_128=_Hash_Get(
                payload,
                "generation_profile_hash_128",
            ),
        )

    @property
    def package_schema_version(self) -> int:
        return (self.package_schema_major << 16) | self.package_schema_minor

    @property
    def container_version(self) -> str:
        return f"{self.container_format_major}.{self.container_format_minor}.0"

    def PackageExactMatch_Validate(self, package: Any) -> None:
        expected_schema = (
            int(package.package_schema_major),
            int(package.package_schema_minor),
        )
        actual_schema = (self.package_schema_major, self.package_schema_minor)
        if actual_schema != expected_schema:
            raise DecoderProfileError(
                "decoder_profile_schema_mismatch",
                f"log={actual_schema[0]}.{actual_schema[1]}:"
                f"package={expected_schema[0]}.{expected_schema[1]}",
            )
        if not _ContainerDescriptor_MatchesPackage(self, package):
            raise DecoderProfileError(
                "decoder_profile_container_version_mismatch",
                f"log={self.container_format_major}.{self.container_format_minor}:"
                f"package={package.required_container_version_range}",
            )
        hash_pairs = (
            (
                "record_catalog",
                self.record_catalog_hash_128,
                package.record_catalog_hash_128,
            ),
            (
                "project_semantics",
                self.project_semantics_hash_128,
                package.project_semantics_hash_128,
            ),
            (
                "generation_profile",
                self.generation_profile_hash_128,
                package.generation_profile_hash_128,
            ),
        )
        for hash_name, actual, expected in hash_pairs:
            if actual != expected:
                raise DecoderProfileError(
                    "decoder_profile_hash_mismatch",
                    f"{hash_name}:log={actual}:package={expected}",
                )

    def Package_IsExactMatch(self, package: Any) -> bool:
        try:
            self.PackageExactMatch_Validate(package)
        except DecoderProfileError:
            return False
        return True

    @classmethod
    def FromRawPayload(
        cls,
        record_type: int,
        record_version: int,
        payload: bytes,
    ) -> DecoderProfileDescriptor | None:
        if record_type != DECODER_PROFILE_DESCRIPTOR_RECORD_TYPE:
            return None
        if record_version != DECODER_PROFILE_DESCRIPTOR_RECORD_VERSION:
            raise DecoderProfileError(
                "decoder_profile_descriptor_version_unsupported",
                str(record_version),
            )
        if len(payload) != DECODER_PROFILE_DESCRIPTOR_PAYLOAD_SIZE:
            raise DecoderProfileError(
                "decoder_profile_descriptor_payload_size_invalid",
                str(len(payload)),
            )
        package_major = int.from_bytes(payload[0:2], "little")
        package_minor = int.from_bytes(payload[2:4], "little")
        container_major = int.from_bytes(payload[4:6], "little")
        container_minor = int.from_bytes(payload[6:8], "little")
        if any(payload[56:64]):
            raise DecoderProfileError(
                "decoder_profile_descriptor_reserved_nonzero"
            )
        return cls(
            package_schema_major=package_major,
            package_schema_minor=package_minor,
            container_format_major=container_major,
            container_format_minor=container_minor,
            record_catalog_hash_128=payload[8:24].hex(),
            project_semantics_hash_128=payload[24:40].hex(),
            generation_profile_hash_128=payload[40:56].hex(),
        )


def _PackageSchema_Get(payload: Mapping[str, Any]) -> tuple[int, int]:
    major = payload.get("package_schema_major")
    minor = payload.get("package_schema_minor")
    if all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (major, minor)
    ):
        return major, minor
    raise DecoderProfileError(
        "decoder_profile_descriptor_field_missing",
        "package_schema_major",
    )


def _ContainerVersion_Get(payload: Mapping[str, Any]) -> tuple[int, int]:
    major = payload.get("container_format_major")
    minor = payload.get("container_format_minor")
    if all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (major, minor)
    ):
        return major, minor
    raise DecoderProfileError(
        "decoder_profile_descriptor_field_missing",
        "container_format_major",
    )


def _ContainerDescriptor_MatchesPackage(
    descriptor: DecoderProfileDescriptor,
    package: Any,
) -> bool:
    from silverstar_flp.decoder_profiles.package import ContainerVersion_IsCompatible

    return ContainerVersion_IsCompatible(
        descriptor.container_version,
        package.required_container_version_range,
    )


def _Hash_Get(payload: Mapping[str, Any], name: str) -> str:
    if name in payload:
        return _Hash_Normalize(payload[name], name)
    raise DecoderProfileError(
        "decoder_profile_descriptor_field_missing",
        name,
    )


def _Hash_Normalize(value: Any, field_name: str) -> str:
    if isinstance(value, str):
        normalized = value.removeprefix("0x").replace("-", "").lower()
        if _HASH128_PATTERN.fullmatch(normalized):
            return normalized
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw_bytes = bytes(value)
        if len(raw_bytes) == 16:
            return raw_bytes.hex()
    if isinstance(value, Sequence) and not isinstance(value, str):
        values = tuple(value)
        if len(values) == 16 and all(
            isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 0xFF
            for item in values
        ):
            return bytes(values).hex()
    raise DecoderProfileError(
        "decoder_profile_descriptor_hash_invalid",
        field_name,
    )
