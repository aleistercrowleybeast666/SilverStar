"""Logical run removal and explicit verified recovery; no physical reclamation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from silverstar_flp.core.analysis_source import (
    ReplayResultChangeResult, ReplayResultStore, RunIdentityState_Validate,
)


def RunHistory_Validate(document) -> None:
    RunIdentityState_Validate(document.run_identity_state)
    history, sources = document.removed_results, document.recovery_sources
    if (not isinstance(history, dict) or len(history) > 4096
            or set(history) != set(document.run_identity_state["deleted"])):
        raise ValueError("project_run_history_invalid")
    if (not isinstance(sources, dict) or len(sources) > 4096 or set(sources) & set(history)):
        raise ValueError("project_run_recovery_sources_invalid")
    RunIdentityState_Validate({"limits": document.run_identity_state["limits"], "deleted": list(sources)})
    for item in history.values():
        _HistoryItem_Validate(document, item)
    from silverstar_flp.plugins.api.algorithm import ReplayMode
    for result_id, item in sources.items():
        _HistoryItem_Validate(document, item)
        if item["configuration"] is None or item["backup"] is None:
            raise ValueError("project_run_recovery_sources_invalid")
        configuration = item["configuration"]
        mode_key = {ReplayMode.WHAT_IF: "what_if", ReplayMode.OFFLINE: "offline",
                    ReplayMode.RECORDED_CONFIGURATION: "recomputed"}[ReplayMode(configuration["mode"])]
        namespace = configuration["algorithm_id"].rsplit(".", 1)[-1] + ":" + mode_key
        if result_id.rpartition(":")[0] != namespace:
            raise ValueError("project_run_recovery_sources_identity_invalid")


def _HistoryItem_Validate(document, item) -> None:
    from silverstar_flp.core.artifacts import ArtifactPath_Resolve
    from silverstar_flp.core.project import ReplayConfiguration_Validate, _Reference_Decode
    if (not isinstance(item, dict) or set(item) != {"algorithm_name", "configuration", "backup"}
            or not isinstance(item["algorithm_name"], str) or len(item["algorithm_name"]) > 1024):
        raise ValueError("project_run_history_invalid")
    if item["configuration"] is not None:
        ReplayConfiguration_Validate(item["configuration"])
    backup = item["backup"]
    if backup is None:
        return
    if not isinstance(backup, dict) or set(backup) != {"project_reference", "artifact_reference"}:
        raise ValueError("project_run_backup_invalid")
    origin = backup["project_reference"]
    if origin is not None and (not isinstance(origin, str) or not origin or len(origin) > 4096):
        raise ValueError("project_run_backup_invalid")
    if document.project_path is None:
        raise ValueError("project_run_backup_invalid")
    origin_path = document.project_path if origin is None else _Reference_Decode(origin, document.project_path)
    if not isinstance(backup["artifact_reference"], dict):
        raise ValueError("project_run_backup_invalid")
    ArtifactPath_Resolve(origin_path, backup["artifact_reference"])


def _RunConfiguration_Get(entry):
    from silverstar_flp.core.project import ReplayConfiguration_Validate
    configuration = {"algorithm_id": entry.algorithm_id, "algorithm_version": entry.algorithm_version,
        "mode": entry.mode.value, "input_source": entry.input_source, "actual_values": dict(entry.parameters),
        "parameter_schema_identity": entry.diagnostics.get("parameter_schema_identity"),
        "provenance": entry.diagnostics.get("config_source")}
    for field, diagnostic in (("quality_policy_revision", "quality_policy_override"),
                               ("process_model_revision", "process_model_revision")):
        if entry.diagnostics.get(diagnostic) is not None:
            configuration[field] = entry.diagnostics[diagnostic]
    ReplayConfiguration_Validate(configuration)
    return configuration


def RunRecovery_SourceCreate(entry, backup) -> dict:
    return {"algorithm_name": entry.algorithm_name, "configuration": _RunConfiguration_Get(entry),
            "backup": deepcopy(backup)}


def ProjectRun_Remove(document, store: ReplayResultStore, result_id: str):
    entry = store.Entry_Get(result_id)
    if entry is None:
        return ReplayResultChangeResult.NOT_FOUND
    configuration = _RunConfiguration_Get(entry)
    source = document.recovery_sources.get(result_id)
    if source is not None and source["configuration"] != configuration:
        return ReplayResultChangeResult.CONFLICT
    backup = deepcopy(source["backup"]) if source is not None else None
    # A saved bundle is only a recovery candidate. Recovery later verifies its
    # identity and exact run membership; it never substitutes another run.
    if backup is None and document.result_artifact is not None and document.project_path is not None:
        backup = {"project_reference": None,
                  "artifact_reference": deepcopy(document.result_artifact)}
    status = store.Result_Remove(result_id)
    if status != ReplayResultChangeResult.REMOVED:
        return status
    document.removed_results[result_id] = {"algorithm_name": entry.algorithm_name,
                                           "configuration": configuration, "backup": backup}
    document.recovery_sources.pop(result_id, None)
    document.run_identity_state = store.IdentityState_Get()
    document.replay_configurations.pop(result_id, None)
    if document.ui_state.get("secondary_source") == entry.source_id:
        document.ui_state["secondary_source"] = None
    document.restored_results = tuple(e for e in document.restored_results if e.result_id != result_id)
    return status


def ProjectRun_BackupLoad(document, result_id: str, context=None):
    from silverstar_flp.core.project import ProjectResults_Load, _Reference_Decode
    RunHistory_Validate(document)
    item = document.removed_results.get(result_id)
    if item is None or item["backup"] is None:
        raise ValueError("project_run_backup_unavailable")
    backup = item["backup"]
    origin = backup["project_reference"]
    origin_path = document.project_path if origin is None else _Reference_Decode(origin, document.project_path)
    candidate = replace(document, project_path=origin_path,
        log_reference=str(document.LogPath_Resolve()), result_artifact=backup["artifact_reference"],
        replay_configurations=({result_id: item["configuration"]} if item["configuration"] else {}),
        run_identity_state={"limits": {}, "deleted": []}, removed_results={}, recovery_sources={}, restored_results=())
    entry = ProjectResults_Load(candidate, context).Entry_Get(result_id)
    if entry is None:
        raise ValueError("project_run_backup_unavailable")
    return entry


def ProjectRun_Restore(document, store: ReplayResultStore, entry):
    item = document.removed_results.get(entry.result_id)
    if item is None:
        return ReplayResultChangeResult.NOT_DELETED
    configuration = _RunConfiguration_Get(entry)
    if item["configuration"] is not None and item["configuration"] != configuration:
        return ReplayResultChangeResult.CONFLICT
    status = store.Result_Restore(entry)
    if status == ReplayResultChangeResult.RESTORED:
        document.replay_configurations[entry.result_id] = configuration
        if item["backup"] is not None:
            document.recovery_sources[entry.result_id] = RunRecovery_SourceCreate(entry, item["backup"])
        del document.removed_results[entry.result_id]
        document.run_identity_state = store.IdentityState_Get()
    return status


def RunHistory_SaveAs(document, project_path: Path, context, *, regenerated=()) -> tuple[dict, dict]:
    """Copy verified backups for data Save As; config-only explicitly depends on origin."""
    from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Write
    from silverstar_flp.core.project import (
        ProjectNumericalIdentity_Get, _Reference_Decode, _Reference_Encode,
    )
    history = deepcopy(document.removed_results)
    sources = {key: deepcopy(value) for key, value in document.recovery_sources.items() if key not in regenerated}
    if document.project_path == project_path:
        return history, sources
    copied = {}
    from itertools import chain
    for item in chain(history.values(), sources.values()):
        backup = item["backup"]
        if backup is None:
            continue
        origin = backup["project_reference"]
        origin_path = document.project_path if origin is None else _Reference_Decode(origin, document.project_path)
        if document.save_data_and_results:
            key = (str(origin_path), backup["artifact_reference"]["path"],
                   backup["artifact_reference"]["sha256"])
            if key not in copied:
                identity = ProjectNumericalIdentity_Get(document, context)
                data = Artifact_Read(origin_path, backup["artifact_reference"], identity, context)
                copied[key] = Artifact_Write(project_path, data, identity, context)
            item["backup"] = {"project_reference": None, "artifact_reference": copied[key]}
        else:
            backup["project_reference"] = _Reference_Encode(origin_path, project_path)
    return history, sources
