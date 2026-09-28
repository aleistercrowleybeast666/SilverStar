from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCacheReference

PROJECT_FORMAT = "SilverStar_FLP_Project"
PROJECT_VERSION = 3


def _Reference_Encode(source_path: Path, project_path: Path | None) -> str:
    path = Path(source_path).resolve()
    if project_path is None:
        return str(path)
    try:
        return str(path.relative_to(project_path.parent.resolve()))
    except ValueError:
        return str(path)


def _Reference_Decode(reference: str, project_path: Path | None) -> Path:
    path = Path(reference)
    if path.is_absolute() or project_path is None:
        return path.resolve()
    return (project_path.parent / path).resolve()


def _String_Require(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"project_{field_name}_invalid")
    return value


@dataclass(frozen=True, slots=True)
class ProjectDecoderProfile:
    source_reference: str | None
    cache_reference: DecoderProfileCacheReference
    package_sha256: str
    generation_profile_sha256: str
    record_catalog_sha256: str
    record_catalog_hash_128: str
    project_semantics_sha256: str
    project_semantics_hash_128: str
    container_plugin_id: str
    container_plugin_version: str
    exact_match_mode: str

    def __post_init__(self) -> None:
        hash_fields = (
            ("package_sha256", self.package_sha256, 64),
            ("generation_profile_sha256", self.generation_profile_sha256, 64),
            ("record_catalog_sha256", self.record_catalog_sha256, 64),
            ("record_catalog_hash_128", self.record_catalog_hash_128, 32),
            ("project_semantics_sha256", self.project_semantics_sha256, 64),
            ("project_semantics_hash_128", self.project_semantics_hash_128, 32),
        )
        for field_name, value, length in hash_fields:
            if len(value) != length or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"project_{field_name}_invalid")
        if self.exact_match_mode != "exact_generation_profile":
            raise ValueError("project_decoder_match_mode_invalid")
        if not self.container_plugin_id or not self.container_plugin_version:
            raise ValueError("project_decoder_container_invalid")

    def SourcePath_Resolve(self, project_path: Path | None) -> Path | None:
        if self.source_reference is None:
            return None
        return _Reference_Decode(self.source_reference, project_path)

    def ToDict(self) -> dict[str, Any]:
        return {
            "source_reference": self.source_reference,
            "cache_reference": self.cache_reference.to_dict(),
            "package_sha256": self.package_sha256,
            "generation_profile_sha256": self.generation_profile_sha256,
            "record_catalog_sha256": self.record_catalog_sha256,
            "record_catalog_hash_128": self.record_catalog_hash_128,
            "project_semantics_sha256": self.project_semantics_sha256,
            "project_semantics_hash_128": self.project_semantics_hash_128,
            "container_plugin_id": self.container_plugin_id,
            "container_plugin_version": self.container_plugin_version,
            "exact_match_mode": self.exact_match_mode,
        }

    @classmethod
    def FromDict(cls, payload: Any) -> ProjectDecoderProfile:
        if not isinstance(payload, dict):
            raise ValueError("project_decoder_profile_invalid")
        cache_payload = payload.get("cache_reference")
        if not isinstance(cache_payload, dict):
            raise ValueError("project_decoder_cache_reference_invalid")
        source_reference = payload.get("source_reference")
        if source_reference is not None and not isinstance(source_reference, str):
            raise ValueError("project_decoder_source_reference_invalid")
        cache_reference = DecoderProfileCacheReference(
            generation_profile_sha256=_String_Require(
                cache_payload,
                "generation_profile_sha256",
            ),
            package_sha256=_String_Require(cache_payload, "package_sha256"),
            relative_path=_String_Require(cache_payload, "relative_path"),
        )
        return cls(
            source_reference=source_reference,
            cache_reference=cache_reference,
            package_sha256=_String_Require(payload, "package_sha256"),
            generation_profile_sha256=_String_Require(
                payload,
                "generation_profile_sha256",
            ),
            record_catalog_sha256=_String_Require(
                payload,
                "record_catalog_sha256",
            ),
            record_catalog_hash_128=_String_Require(
                payload,
                "record_catalog_hash_128",
            ),
            project_semantics_sha256=_String_Require(
                payload,
                "project_semantics_sha256",
            ),
            project_semantics_hash_128=_String_Require(
                payload,
                "project_semantics_hash_128",
            ),
            container_plugin_id=_String_Require(
                payload,
                "container_plugin_id",
            ),
            container_plugin_version=_String_Require(
                payload,
                "container_plugin_version",
            ),
            exact_match_mode=_String_Require(payload, "exact_match_mode"),
        )


@dataclass(slots=True)
class ProjectDocument:
    log_reference: str = ""
    decoder_profile: ProjectDecoderProfile | None = None
    replay_configurations: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""
    ui_state: dict[str, Any] = field(default_factory=dict)
    project_path: Path | None = None

    def LogReference_Set(self, log_path: Path) -> None:
        self.log_reference = _Reference_Encode(log_path, self.project_path)

    def LogPath_Resolve(self) -> Path:
        if not self.log_reference:
            raise ValueError("project_log_reference_missing")
        return _Reference_Decode(self.log_reference, self.project_path)

    def DecoderSourcePath_Resolve(self) -> Path | None:
        if self.decoder_profile is None:
            return None
        return self.decoder_profile.SourcePath_Resolve(self.project_path)


def ReplayConfiguration_Validate(configuration: Any) -> None:
    from silverstar_flp.plugins.api.algorithm import ReplayMode
    from silverstar_flp.plugins.registry import builtin_registry

    fields = {
        "algorithm_id",
        "algorithm_version",
        "mode",
        "input_source",
        "actual_values",
        "parameter_schema_identity",
        "provenance",
    }
    if not isinstance(configuration, dict) or set(configuration) not in (
        fields,
        fields | {"quality_policy_revision"},
    ):
        raise ValueError("project_replay_configuration_invalid")
    try:
        plugin = builtin_registry().Algorithm_Get(configuration["algorithm_id"])
    except (KeyError, TypeError) as exc:
        raise ValueError("project_algorithm_unknown") from exc
    if configuration[
        "algorithm_version"
    ] != plugin.metadata.version or not plugin.ParameterSchemaCompatible_Is(
        configuration["parameter_schema_identity"]
    ):
        raise ValueError("project_parameter_schema_mismatch")
    if configuration["mode"] == "integrity_assisted":
        raise ValueError("project_legacy_integrity_assistance_unsupported")
    ReplayMode(configuration["mode"])
    if "quality_policy_revision" in configuration and (
        configuration["mode"] != ReplayMode.WHAT_IF
        or type(configuration["quality_policy_revision"]) is not int
        or configuration["quality_policy_revision"] not in plugin.metadata.what_if_quality_revisions
    ):
        raise ValueError("project_quality_policy_revision_invalid")
    if configuration["input_source"] not in ("corrected_imu", "recorded_inertial_increment"):
        raise ValueError("project_replay_input_invalid")
    if configuration["provenance"] not in (
        "Firmware build configuration from .ssdecoder",
        "Algorithm Plugin actual defaults",
    ):
        raise ValueError("project_parameter_provenance_invalid")
    if not isinstance(configuration["actual_values"], dict):
        raise ValueError("project_actual_values_invalid")
    plugin.metadata.Parameters_Validate(configuration["actual_values"])


def Project_Save(document: ProjectDocument, path: Path) -> None:
    if document.decoder_profile is None:
        raise ValueError("project_decoder_profile_missing")
    for configuration in document.replay_configurations.values():
        ReplayConfiguration_Validate(configuration)
    project_path = Path(path).resolve()
    project_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_log_path = document.LogPath_Resolve()
    resolved_source_path = document.DecoderSourcePath_Resolve()
    encoded_log_reference = _Reference_Encode(resolved_log_path, project_path)
    decoder_payload = document.decoder_profile.ToDict()
    decoder_payload["source_reference"] = (
        _Reference_Encode(resolved_source_path, project_path)
        if resolved_source_path is not None
        else None
    )
    payload = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "log_reference": encoded_log_reference,
        "decoder_profile": decoder_payload,
        "replay_configurations": document.replay_configurations,
        "notes": document.notes,
        "ui_state": document.ui_state,
    }
    temporary_path = project_path.parent / (f".{project_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, project_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    document.project_path = project_path
    document.log_reference = encoded_log_reference
    document.decoder_profile = _DecoderProfile_SourceReplace(
        document.decoder_profile,
        decoder_payload["source_reference"],
    )


def _DecoderProfile_SourceReplace(
    profile: ProjectDecoderProfile,
    source_reference: str | None,
) -> ProjectDecoderProfile:
    return ProjectDecoderProfile(
        source_reference=source_reference,
        cache_reference=profile.cache_reference,
        package_sha256=profile.package_sha256,
        generation_profile_sha256=profile.generation_profile_sha256,
        record_catalog_sha256=profile.record_catalog_sha256,
        record_catalog_hash_128=profile.record_catalog_hash_128,
        project_semantics_sha256=profile.project_semantics_sha256,
        project_semantics_hash_128=profile.project_semantics_hash_128,
        container_plugin_id=profile.container_plugin_id,
        container_plugin_version=profile.container_plugin_version,
        exact_match_mode=profile.exact_match_mode,
    )


def Project_Load(path: Path) -> ProjectDocument:
    project_path = Path(path).resolve()
    try:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"project_read_failed:{exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT:
        raise ValueError("project_format_invalid")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("project_version_unsupported")
    if version != PROJECT_VERSION:
        raise ValueError("project_version_unsupported")
    log_reference = payload.get("log_reference")
    if not isinstance(log_reference, str) or not log_reference:
        raise ValueError("project_log_reference_missing")
    replay = payload.get("replay_configurations", {})
    ui_state = payload.get("ui_state", {})
    if not isinstance(replay, dict) or not isinstance(ui_state, dict):
        raise ValueError("project_state_invalid")
    for configuration in replay.values():
        ReplayConfiguration_Validate(configuration)
    return ProjectDocument(
        log_reference=log_reference,
        decoder_profile=ProjectDecoderProfile.FromDict(payload.get("decoder_profile")),
        replay_configurations=dict(replay),
        notes=str(payload.get("notes", "")),
        ui_state=dict(ui_state),
        project_path=project_path,
    )


def Project_ToDict(document: ProjectDocument) -> dict[str, Any]:
    return {
        "log_reference": document.log_reference,
        "decoder_profile": (
            document.decoder_profile.ToDict() if document.decoder_profile is not None else None
        ),
        "replay_configurations": document.replay_configurations,
        "notes": document.notes,
        "ui_state": document.ui_state,
        "project_path": (str(document.project_path) if document.project_path is not None else None),
    }
