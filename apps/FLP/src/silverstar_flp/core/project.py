from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
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
    result_artifact: dict[str, Any] | None = None
    parse_artifact: dict[str, Any] | None = None
    restored_results: tuple = ()
    restoration_issues: tuple[str, ...] = ()
    save_data_and_results: bool = True
    run_identity_state: dict = field(default_factory=lambda: {"limits": {}, "deleted": []})
    removed_results: dict = field(default_factory=dict)
    recovery_sources: dict = field(default_factory=dict)
    saved_result_ids: tuple[str, ...] = ()  # Runtime membership proof; never trusted from project JSON.

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
    optional_fields = {"quality_policy_revision", "process_model_revision"}
    if not isinstance(configuration, dict) or not (
        fields <= set(configuration) <= fields | optional_fields
    ):
        raise ValueError("project_replay_configuration_invalid")
    try:
        plugin = builtin_registry().Algorithm_Get(configuration["algorithm_id"])
    except (KeyError, TypeError) as exc:
        raise ValueError("project_algorithm_unknown") from exc
    if (configuration["algorithm_id"] == "silverstar.algorithm.sf6"
            and configuration["algorithm_version"] == "0.1.0-c-core-revision1"):
        from silverstar_flp.plugins.algorithms.sf6.legacy_plugin import Sf6AlgorithmPlugin
        plugin = Sf6AlgorithmPlugin()
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
    if "process_model_revision" in configuration and (
        type(configuration["process_model_revision"]) is not int
        or configuration["process_model_revision"] not in plugin.metadata.process_model_revisions
    ):
        raise ValueError("project_process_model_revision_invalid")
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


def Project_Save(document: ProjectDocument, path: Path, *, replay_store=None,
                 dataset=None, context=None) -> None:
    from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Write
    from silverstar_flp.core.context import TaskContext
    task_context = context or TaskContext()
    from silverstar_flp.core.task_progress import TaskProgress
    progress = TaskProgress(task_context)
    progress.Progress_Report(0.02, "progress.save.prepare")
    from copy import deepcopy
    from silverstar_flp.core.run_history import RunHistory_Validate, RunHistory_SaveAs
    from silverstar_flp.core.analysis_source import RunIdentityState_Validate
    RunHistory_Validate(document)
    run_state = deepcopy(document.run_identity_state)
    if replay_store is not None:
        run_state = replay_store.IdentityState_Get()
        # Never forget identities reserved by an older/config-only project.
        for key, value in document.run_identity_state["limits"].items():
            run_state["limits"][key] = max(value, run_state["limits"].get(key, 0))
    RunIdentityState_Validate(run_state)
    if set(run_state["deleted"]) != set(document.removed_results):
        raise ValueError("project_run_history_invalid")
    replay_configurations = {key: value for key, value in document.replay_configurations.items()
                             if key not in run_state["deleted"]}
    if document.decoder_profile is None:
        raise ValueError("project_decoder_profile_missing")
    for configuration in replay_configurations.values():
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
    saved_entries = None
    progress.Progress_Report(0.04, "progress.save.references")
    result_artifact = document.result_artifact if document.save_data_and_results else None
    parse_artifact = document.parse_artifact if document.save_data_and_results else None
    if dataset is not None and document.save_data_and_results:
        from silverstar_flp.core.parse_cache import DatasetCache_Write, ParseIdentity_Get
        decoder_identity = {key: value for key, value in document.decoder_profile.ToDict().items()
                            if key not in ("source_reference", "cache_reference")}
        parse_identity = ParseIdentity_Get(resolved_log_path, decoder_identity, progress.Context_Build(0.04, 0.08))
        # Store the complete parsed object once, shared by every result in this project.
        progress.Progress_Report(0.08, "progress.save.dataset")
        parse_artifact = DatasetCache_Write(project_path, dataset, parse_identity,
                                           progress.Context_Build(0.08, 0.40))
    elif parse_artifact is not None and document.project_path != project_path:
        from silverstar_flp.core.parse_cache import DatasetCache_Read, DatasetCache_Write, ParseIdentity_Get
        decoder_identity = {key: value for key, value in document.decoder_profile.ToDict().items()
                            if key not in ("source_reference", "cache_reference")}
        identity = ParseIdentity_Get(resolved_log_path, decoder_identity, task_context)
        saved_dataset = DatasetCache_Read(document.project_path, parse_artifact, identity,
                                         resolved_log_path, progress.Context_Build(0.08, 0.18))
        parse_artifact = DatasetCache_Write(project_path, saved_dataset, identity,
                                           progress.Context_Build(0.18, 0.40))
    progress.Progress_Report(0.40, "progress.save.results" if document.save_data_and_results
                             else "progress.save.configuration")
    if replay_store is not None and document.save_data_and_results:
        if document.restoration_issues:
            # Do not replace unavailable saved history with an incomplete current store.
            raise ValueError("project_saved_results_unavailable")
        identity = ProjectNumericalIdentity_Get(document, progress.Context_Build(0.40, 0.44))
        entries = replay_store.Entries_Get()
        if entries and dataset is None:
            raise ValueError("project_result_input_identity_missing")
        for entry in entries:
            if (entry.diagnostics.get("input_identity") != dataset.metadata.get("parse_identity")
                    or entry.diagnostics.get("input_identity") is None
                    or entry.diagnostics.get("engine_identity") != identity["engine_identity"]):
                raise ValueError("project_result_input_identity_mismatch")
        stored = tuple({"result_id": entry.result_id, "source_id": entry.source_id,
                        "run_index": entry.run_index, "algorithm_name": entry.algorithm_name,
                        "result": entry.result} for entry in entries)
        result_artifact = Artifact_Write(project_path, stored, identity,
                                         progress.Context_Build(0.45, 0.78))
        saved_entries = entries
    elif result_artifact is not None and (document.project_path != project_path or run_state["deleted"]):
        # Save As copies only verified numerical artifacts, never log/decoder payloads.
        identity = ProjectNumericalIdentity_Get(document, progress.Context_Build(0.40, 0.44))
        stored = Artifact_Read(document.project_path, result_artifact, identity,
                               progress.Context_Build(0.45, 0.60))
        if not isinstance(stored, tuple) or any(not isinstance(item, dict) for item in stored):
            raise ValueError("project_result_table_invalid")
        retained = tuple(item for item in stored if item.get("result_id") not in run_state["deleted"])
        if len(retained) != len(stored) or document.project_path != project_path:
            result_artifact = Artifact_Write(project_path, retained, identity,
                                             progress.Context_Build(0.60, 0.78))
    progress.Progress_Report(0.78, "progress.save.history")
    removed_results, recovery_sources = RunHistory_SaveAs(document, project_path,
        progress.Context_Build(0.78, 0.90),
        regenerated=tuple(entry.result_id for entry in saved_entries) if saved_entries is not None else ())
    if saved_entries is not None:
        from silverstar_flp.core.run_history import RunRecovery_SourceCreate
        for entry in saved_entries:
            recovery_sources[entry.result_id] = RunRecovery_SourceCreate(entry,
                {"project_reference": None, "artifact_reference": result_artifact})
    saved_result_ids = ()
    if document.save_data_and_results:
        saved_result_ids = (tuple(entry.result_id for entry in saved_entries) if saved_entries is not None
            else tuple(key for key in document.saved_result_ids if key not in run_state["deleted"]))
    # Admit the merged/rebased metadata too, before publishing a project that
    # would otherwise exceed the same limits checked by Project_Load.
    RunHistory_Validate(replace(document, project_path=project_path,
        run_identity_state=run_state, removed_results=removed_results, recovery_sources=recovery_sources))
    payload = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "log_reference": encoded_log_reference,
        "decoder_profile": decoder_payload,
        "replay_configurations": replay_configurations,
        "notes": document.notes,
        "ui_state": document.ui_state,
        "result_artifact": result_artifact,
        "parse_artifact": parse_artifact,
        "save_data_and_results": document.save_data_and_results,
        "run_identity_state": run_state,
        "removed_results": removed_results,
        "recovery_sources": recovery_sources,
    }
    temporary_path = project_path.parent / (f".{project_path.name}.{uuid.uuid4().hex[:8]}.tmp")
    progress.Progress_Report(0.92, "progress.save.project")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        task_context.Cancel_RaiseIfRequested()
        if dataset is not None and document.save_data_and_results:
            progress.Progress_Report(0.95, "progress.save.source_check")
            from silverstar_flp.core.artifacts import FileHash_Get
            if FileHash_Get(resolved_log_path, progress.Context_Build(0.95, 0.97), quantified=True) != dataset.metadata["parse_identity"]["log_sha256"]:
                raise ValueError("project_result_input_identity_mismatch")
        progress.Progress_Report(0.98, "progress.save.commit")
        task_context.Cancel_RaiseIfRequested()
        os.replace(temporary_path, project_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    document.project_path = project_path
    document.result_artifact = result_artifact
    document.parse_artifact = parse_artifact
    document.replay_configurations = replay_configurations
    document.run_identity_state = run_state
    document.removed_results = removed_results
    document.recovery_sources = recovery_sources
    document.saved_result_ids = saved_result_ids
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
    save_data_and_results = payload.get("save_data_and_results", True)
    if type(save_data_and_results) is not bool:
        raise ValueError("project_save_data_option_invalid")
    if not save_data_and_results and any(payload.get(name) is not None for name in
                                         ("result_artifact", "parse_artifact")):
        raise ValueError("project_configuration_only_artifact_invalid")
    from silverstar_flp.core.artifacts import ArtifactPath_Resolve
    for field_name in ("result_artifact", "parse_artifact"):
        reference = payload.get(field_name)
        if reference is not None:
            if not isinstance(reference, dict):
                raise ValueError("project_artifact_reference_invalid")
            ArtifactPath_Resolve(project_path, reference)
    document = ProjectDocument(
        log_reference=log_reference,
        decoder_profile=ProjectDecoderProfile.FromDict(payload.get("decoder_profile")),
        replay_configurations=dict(replay),
        notes=str(payload.get("notes", "")),
        ui_state=dict(ui_state),
        project_path=project_path,
        result_artifact=payload.get("result_artifact"),
        parse_artifact=payload.get("parse_artifact"),
        save_data_and_results=save_data_and_results,
        run_identity_state=payload.get("run_identity_state", {"limits": {}, "deleted": []}),
        removed_results=payload.get("removed_results", {}),
        recovery_sources=payload.get("recovery_sources", {}),
    )
    from silverstar_flp.core.run_history import RunHistory_Validate
    RunHistory_Validate(document)
    # Old v3 config-only projects also reserve their previously assigned IDs.
    import re
    for result_id in replay:
        if isinstance(result_id, str) and re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}:(?:what_if|offline|recomputed):[1-9][0-9]{0,9}", result_id):
            key, _, index = result_id.rpartition(":")
            if int(index) > 2**31 - 1:
                raise ValueError("project_run_identity_invalid")
            limits = document.run_identity_state["limits"]
            limits[key] = max(int(index), limits.get(key, 0))
    if set(replay) & set(document.run_identity_state["deleted"]):
        raise ValueError("project_deleted_run_configuration_present")
    RunHistory_Validate(document)
    return document


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
        "result_artifact": document.result_artifact,
        "parse_artifact": document.parse_artifact,
        "save_data_and_results": document.save_data_and_results,
        "run_identity_state": document.run_identity_state,
        "removed_results": document.removed_results,
        "recovery_sources": document.recovery_sources,
    }


def ProjectNumericalIdentity_Get(document: ProjectDocument, context=None) -> dict:
    from silverstar_flp.core.artifacts import EngineIdentity_Get, FileHash_Get
    if document.decoder_profile is None:
        raise ValueError("project_decoder_profile_missing")
    from silverstar_flp.core.parse_cache import ParserIdentity_Get
    return {"log_sha256": FileHash_Get(document.LogPath_Resolve(), context),
            "decoder": {key: value for key, value in document.decoder_profile.ToDict().items()
                        if key not in ("source_reference", "cache_reference")},
            "engine_identity": EngineIdentity_Get(), "parser_identity": ParserIdentity_Get()}


def DecoderNumericalIdentity_Get(package, container) -> dict:
    return {"package_sha256": package.package_sha256,
            "generation_profile_sha256": package.generation_profile_sha256,
            "record_catalog_sha256": package.checksums["record_catalog.json"],
            "record_catalog_hash_128": package.record_catalog_hash_128,
            "project_semantics_sha256": package.checksums["project_semantics.json"],
            "project_semantics_hash_128": package.project_semantics_hash_128,
            "container_plugin_id": container.metadata.plugin_id,
            "container_plugin_version": container.metadata.version,
            "exact_match_mode": "exact_generation_profile"}


def ProjectResults_Load(document: ProjectDocument, context=None):
    """Load every completed run; absence/corruption never launches numerical replay."""
    from silverstar_flp.core.analysis_source import ReplayResultStore
    from silverstar_flp.core.artifacts import Artifact_Read
    from silverstar_flp.plugins.api.algorithm import AlgorithmResult
    store = ReplayResultStore()
    if document.result_artifact is None:
        store.IdentityState_Restore(document.run_identity_state)
        document.saved_result_ids = ()
        return store
    payload = Artifact_Read(document.project_path, document.result_artifact,
                            ProjectNumericalIdentity_Get(document, context), context)
    from silverstar_flp.core.parse_cache import ParseIdentity_Get
    decoder_identity = {key: value for key, value in document.decoder_profile.ToDict().items()
                        if key not in ("source_reference", "cache_reference")}
    input_identity = ParseIdentity_Get(document.LogPath_Resolve(), decoder_identity, context)
    from silverstar_flp.core.artifacts import EngineIdentity_Get
    engine_identity = EngineIdentity_Get()
    if not isinstance(payload, tuple) or len(payload) > 4096:
        raise ValueError("project_result_table_invalid")
    from silverstar_flp.core.run_history import RunRecovery_SourceCreate
    verified_sources = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("result"), AlgorithmResult):
            raise ValueError("project_result_invalid")
        if item.get("result_id") in document.run_identity_state["deleted"]:
            continue
        entry = store.Result_Add(item["result"], algorithm_name=item["algorithm_name"],
                                 restored_run_index=item["run_index"])
        if entry.result_id != item["result_id"] or entry.source_id != item["source_id"]:
            raise ValueError("project_result_identity_mismatch")
        if (entry.diagnostics.get("input_identity") != input_identity or
                entry.diagnostics.get("engine_identity") != engine_identity):
            raise ValueError("project_result_input_identity_mismatch")
        configuration = document.replay_configurations.get(entry.result_id)
        if configuration is not None and (
                configuration["actual_values"] != dict(entry.parameters)
                or configuration["algorithm_id"] != entry.algorithm_id
                or configuration["algorithm_version"] != entry.algorithm_version
                or configuration["mode"] != entry.mode.value
                or configuration["input_source"] != entry.input_source
                or configuration.get("process_model_revision") != entry.diagnostics.get("process_model_revision")
                or configuration.get("quality_policy_revision") != entry.diagnostics.get("quality_policy_override")
                or configuration["provenance"] != entry.diagnostics.get("config_source")
                or configuration["parameter_schema_identity"] !=
                entry.diagnostics.get("parameter_schema_identity")):
            raise ValueError("project_result_configuration_mismatch")
        verified_sources[entry.result_id] = RunRecovery_SourceCreate(entry,
            {"project_reference": None, "artifact_reference": document.result_artifact})
    store.IdentityState_Restore(document.run_identity_state)
    from silverstar_flp.core.run_history import RunHistory_Validate
    admitted_state = store.IdentityState_Get()
    admitted_sources = {**document.recovery_sources, **verified_sources}
    admitted_saved_ids = tuple(verified_sources)
    RunHistory_Validate(replace(document, run_identity_state=admitted_state,
                                recovery_sources=admitted_sources))
    # Publish all validated metadata together. Legacy artifacts may reserve
    # indices not present in the original v3 document's optional state fields.
    document.run_identity_state = admitted_state
    document.recovery_sources = admitted_sources
    document.saved_result_ids = admitted_saved_ids
    return store
