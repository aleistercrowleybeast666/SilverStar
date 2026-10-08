from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.model import (FEATURE_TIERS, DEFAULT_PROTOCOL_COMPONENTS, DEFAULT_PROTOCOL_PROFILES,
                                          ProjectModel, ProjectModel_Parse, ProtocolSelection)


_ESKF15 = "silverstar.algorithm.estimator.eskf15"
_KF6 = "silverstar.algorithm.estimator.kf6"
_SF6 = "silverstar.algorithm.estimator.sf6"
_BAROMETER = "SYSTEM_DEVICE_CLASS_BAROMETER"
# Explicit producer ownership, not a name-prefix rule. Shared replay inputs
# and diagnostics (ESTIMATOR_STEP, GNSS/BARO_MEASUREMENT, NAV_QUALITY) stay out.
_LOG_ALGORITHM_OWNERS = {
    "FLIGHT_LOG_RECORD_PURE_INS": None,
    "FLIGHT_LOG_RECORD_ESTIMATOR": _KF6,
    "FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC": _KF6,
    "FLIGHT_LOG_RECORD_KF6_FULL_P": _KF6,
    "FLIGHT_LOG_RECORD_SF6_STATE": _SF6,
    "FLIGHT_LOG_RECORD_SF6_MEASUREMENT": _SF6,
    **{"FLIGHT_LOG_RECORD_ESKF15_" + name: _ESKF15 for name in (
        "STATE", "FULL_P_PART", "INITIAL_STATE", "INITIAL_P_PART", "MEASUREMENT", "BODY_INPUT")},
}


def FeatureTier_LogRecordAlgorithmOwned(record: str) -> bool:
    return record in _LOG_ALGORITHM_OWNERS


def FeatureTier_LogRecordReasonGet(model: ProjectModel, record: str) -> str:
    if (record in _LOG_ALGORITHM_OWNERS and
            model.strategies.get("estimator") != _LOG_ALGORITHM_OWNERS[record]):
        return "logging.algorithm.disabled"
    if model.build.feature_tier in ("compact", "minimal") and record == "FLIGHT_LOG_RECORD_TELEMETRY_DIAG":
        return "logging.feature_tier.disabled"
    return ""


def FeatureTier_LogRecordAllowed(model: ProjectModel, record: str) -> bool:
    """First-release policy projects retained choices onto the selected producer."""
    return not FeatureTier_LogRecordReasonGet(model, record)


def FeatureTier_LogRecordRequired(model: ProjectModel, record: str) -> bool:
    """Pure INS needs its recorded navigation output in both bounded tiers."""
    return (model.build.feature_tier in ("compact", "minimal") and
            model.strategies.get("estimator") is None and record == "FLIGHT_LOG_RECORD_PURE_INS")


def FeatureTier_StrategyAllowed(model: ProjectModel, component_id: str | None) -> bool:
    tier = model.build.feature_tier
    return not ((tier != "full" and component_id == _ESKF15) or
                (tier in ("compact", "minimal") and component_id == _KF6))


def FeatureTier_DeviceClassLimitGet(tier: str, component_class: str, category: str,
                                   ordinary_limit: int) -> int:
    if tier == "minimal" and component_class == "gnss":
        return 0
    if tier in ("compact", "minimal") and (
            category.startswith("sensor.") or component_class == "telemetry"):
        return min(1, ordinary_limit)
    return ordinary_limit


def FeatureTier_BarometerOwnerGet(model: ProjectModel, catalog) -> str:
    """A dedicated barometer precedes an embedded barometer in bounded tiers."""
    if not model.build.compact_mode:
        return ""
    for instance in model.device_instances:
        manifest = catalog.InstanceComponent_Get(instance)
        if manifest.component_class == "barometer" and any(
            entry.get("class") == _BAROMETER
            for entry in manifest.metadata.get("device_descriptors", ())
        ):
            return instance.instance_id
    return ""


def FeatureTier_DescriptorActive(model: ProjectModel, catalog, instance_id: str, device_class: str) -> bool:
    if device_class != _BAROMETER:
        return True
    owner = FeatureTier_BarometerOwnerGet(model, catalog)
    if not owner or instance_id == owner:
        return True
    instance = next((item for item in model.device_instances if item.instance_id == instance_id), None)
    # A second dedicated device is a configuration error, never a silently
    # hidden endpoint. Only multifunction embedded barometers are suppressed.
    return instance is not None and catalog.InstanceComponent_Get(instance).component_class == "barometer"


def FeatureTier_ErrorsGet(model: ProjectModel, catalog) -> tuple[str, ...]:
    errors = []
    if not FeatureTier_StrategyAllowed(model, model.strategies.get("estimator")):
        errors.append("Selected estimator is prohibited by the feature tier; retained parameters need explicit review")
    if model.build.feature_tier == "minimal":
        if model.protocols.get("maintenance") is not None:
            errors.append("Minimal tier requires maintenance disabled")
        if (any(catalog.InstanceComponent_Get(instance).component_class == "gnss"
                for instance in model.device_instances) or any(entry.get("class") == "SYSTEM_DEVICE_CLASS_GNSS"
               for instance in model.device_instances
               for entry in catalog.InstanceComponent_Get(instance).metadata.get("device_descriptors", ()))):
            errors.append("Minimal tier requires GNSS inactive")
        if model.protocols.get("logging") is None:
            errors.append("Minimal tier requires the local SSLOG/storage contract")
    return tuple(errors)


def _FeatureTier_DevicesNormalize(model: ProjectModel, catalog) -> tuple[str, ...]:
    """Only an explicit preset switch removes excess active instances, in order."""
    retained, removed, counts = [], [], {}
    for instance in model.device_instances:
        manifest = catalog.InstanceComponent_Get(instance)
        kind = manifest.component_class
        limit = FeatureTier_DeviceClassLimitGet(model.build.feature_tier, kind,
            str(manifest.metadata.get("device_category", "")), 2)
        if model.build.feature_tier == "minimal" and any(
                entry.get("class") == "SYSTEM_DEVICE_CLASS_GNSS"
                for entry in manifest.metadata.get("device_descriptors", ())):
            limit = 0
        count = counts.get(kind, 0)
        if limit <= 1 and count >= limit:
            removed.append(instance.instance_id)
        else:
            retained.append(instance)
            counts[kind] = count + 1
    model.device_instances = retained
    model.capability_source_overrides = {key: value for key, value in
        model.capability_source_overrides.items() if value not in removed}
    model.resource_assignments = {key: value for key, value in model.resource_assignments.items()
        if key.partition(":")[0] not in removed}
    if model.alignment.external_source_instance in removed:
        model.alignment = replace(model.alignment, external_source_instance="")
    if model.air_link.flight_radio_instance in removed:
        first_radio = next((item.instance_id for item in retained
            if catalog.InstanceComponent_Get(item).component_class == "telemetry"), "telemetry0")
        model.air_link = replace(model.air_link, flight_radio_instance=first_radio)
    return tuple("device:removed:" + identity for identity in removed)


def FeatureTier_Apply(model: ProjectModel, tier: str, catalog) -> tuple[str, ...]:
    """An explicit user preset switch saves a reversible, nonrecursive snapshot.

    Hardware/MCU, paths and build tools remain current when restoring selections.
    Snapshots keep original algorithms/parameters/protocol identities; active
    devices are normalized in list order and never restored from a tier snapshot.
    generation sees only the current active model. No load-time algorithm rewrite.
    """
    if tier not in FEATURE_TIERS:
        raise ValueError("Unknown feature tier")
    previous = model.build.feature_tier
    if tier == previous:
        return _FeatureTier_DevicesNormalize(model, catalog)
    snapshot = model.Dictionary_Get()
    snapshot.pop("feature_tier_presets", None)
    model.feature_tier_presets[previous] = snapshot
    notes = []
    if tier in model.feature_tier_presets:
        restored = ProjectModel_Parse(deepcopy(model.feature_tier_presets[tier]))
        for field in ("strategies", "algorithm_parameters", "modes", "mode_parameters",
                      "alignment", "protocols", "logging_streams"):
            setattr(model, field, deepcopy(getattr(restored, field)))
        notes.append("restored")
    model.build = replace(model.build, feature_tier=tier)
    notes.extend(_FeatureTier_DevicesNormalize(model, catalog))
    selected = model.strategies.get("estimator")
    if not FeatureTier_StrategyAllowed(model, selected):
        replacement = _KF6 if tier == "standard" else _SF6
        model.strategies["estimator"] = replacement
        notes.append("estimator:" + str(selected) + "->" + replacement)
    if model.build.compact_mode:
        from silverstar_fccg.project.compact import CompactErrors_Get
        notes.extend(CompactErrors_Get(model, catalog))
        barometer = FeatureTier_BarometerOwnerGet(model, catalog)
        if barometer:
            notes.append("barometer:" + barometer)
    if tier == "minimal":
        model.protocols["maintenance"] = None
        notes.append("maintenance:disabled")
        if model.protocols.get("logging") is None:
            manifest = catalog.Component_Get(DEFAULT_PROTOCOL_COMPONENTS["logging"])
            model.protocols["logging"] = ProtocolSelection(manifest.component_id, manifest.version,
                                                           DEFAULT_PROTOCOL_PROFILES["logging"])
            notes.append("logging:enabled")
    notes.extend(FeatureTier_ErrorsGet(model, catalog))
    return tuple(notes)
