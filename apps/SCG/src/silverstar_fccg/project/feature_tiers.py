from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from silverstar_fccg.project.model import (FEATURE_TIERS, DEFAULT_PROTOCOL_COMPONENTS, DEFAULT_PROTOCOL_PROFILES,
                                          ProjectModel, ProjectModel_Parse, ProtocolSelection)


_ESKF15 = "silverstar.algorithm.estimator.eskf15"
_KF6 = "silverstar.algorithm.estimator.kf6"
_SF6 = "silverstar.algorithm.estimator.sf6"
_BAROMETER = "SYSTEM_DEVICE_CLASS_BAROMETER"
_BOUNDED_CLASSES = frozenset({"SYSTEM_DEVICE_CLASS_IMU", "SYSTEM_DEVICE_CLASS_GNSS",
                             "SYSTEM_DEVICE_CLASS_TELEMETRY", _BAROMETER})


def FeatureTier_LogRecordAllowed(model: ProjectModel, record: str) -> bool:
    """Tier policy projects retained log choices without erasing them."""
    if model.build.feature_tier not in ("compact", "minimal"):
        return True
    return (record != "FLIGHT_LOG_RECORD_TELEMETRY_DIAG" and
            (record != "FLIGHT_LOG_RECORD_PURE_INS" or model.strategies.get("estimator") != _SF6))


def FeatureTier_LogRecordRequired(model: ProjectModel, record: str) -> bool:
    """Pure INS needs its recorded navigation output in both bounded tiers."""
    return (model.build.feature_tier in ("compact", "minimal") and
            model.strategies.get("estimator") is None and record == "FLIGHT_LOG_RECORD_PURE_INS")


def FeatureTier_StrategyAllowed(model: ProjectModel, component_id: str | None) -> bool:
    tier = model.build.feature_tier
    return not ((tier != "full" and component_id == _ESKF15) or
                (tier in ("compact", "minimal") and component_id == _KF6))


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
        if any(entry.get("class") == "SYSTEM_DEVICE_CLASS_GNSS"
               for instance in model.device_instances
               for entry in catalog.InstanceComponent_Get(instance).metadata.get("device_descriptors", ())):
            errors.append("Minimal tier requires GNSS inactive")
        if model.protocols.get("logging") is None:
            errors.append("Minimal tier requires the local SSLOG/storage contract")
    return tuple(errors)


def _BoundedDevices_Get(model: ProjectModel, catalog):
    dedicated = FeatureTier_BarometerOwnerGet(model, catalog)
    occupied: set[str] = set()
    retained = []
    for instance in model.device_instances:
        manifest = catalog.InstanceComponent_Get(instance)
        classes = {entry.get("class") for entry in manifest.metadata.get("device_descriptors", ())} & _BOUNDED_CLASSES
        if dedicated and instance.instance_id != dedicated and manifest.component_class != "barometer":
            # Retain a multifunction IMU while its embedded barometer endpoint
            # is inactive; the generated facade publishes the dedicated source.
            classes.discard(_BAROMETER)
        if classes & occupied:
            continue
        if model.build.feature_tier == "minimal" and "SYSTEM_DEVICE_CLASS_GNSS" in classes:
            continue
        retained.append(instance)
        occupied.update(classes)
    return retained


def FeatureTier_Apply(model: ProjectModel, tier: str, catalog) -> tuple[str, ...]:
    """An explicit user preset switch saves a reversible, nonrecursive snapshot.

    Hardware/MCU, paths and build tools remain current when restoring selections.
    Snapshots keep original algorithms/parameters/devices/protocol identities;
    generation sees only the current active model. No load-time algorithm rewrite.
    """
    if tier not in FEATURE_TIERS:
        raise ValueError("Unknown feature tier")
    previous = model.build.feature_tier
    if tier == previous:
        return ()
    snapshot = model.Dictionary_Get()
    snapshot.pop("feature_tier_presets", None)
    model.feature_tier_presets[previous] = snapshot
    notes = []
    if tier in model.feature_tier_presets:
        restored = ProjectModel_Parse(deepcopy(model.feature_tier_presets[tier]))
        for field in ("device_instances", "strategies", "algorithm_parameters", "modes", "mode_parameters",
                      "alignment", "protocols", "logging_streams", "resource_assignments", "capability_source_overrides"):
            setattr(model, field, deepcopy(getattr(restored, field)))
        notes.append("restored")
    model.build = replace(model.build, feature_tier=tier)
    selected = model.strategies.get("estimator")
    if not FeatureTier_StrategyAllowed(model, selected):
        replacement = _KF6 if tier == "standard" else _SF6
        model.strategies["estimator"] = replacement
        notes.append("estimator:" + str(selected) + "->" + replacement)
    if model.build.compact_mode:
        retained = _BoundedDevices_Get(model, catalog)
        removed = [item.instance_id for item in model.device_instances if item not in retained]
        model.device_instances = retained
        if removed:
            notes.append("suspended:" + ",".join(removed))
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
    return tuple(notes)
