from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
from silverstar_fccg.project.model import LogStreamConfig, ProjectModel

if TYPE_CHECKING:
    from silverstar_fccg.plugins.catalog import PluginCatalog
    from silverstar_fccg.plugins.manifest import PluginManifest


class LogMetadataError(FccgError):
    pass


class LogPolicyLevel(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class LogPurpose(StrEnum):
    FLIGHT = "flight"
    TEST = "test"


class LogCadenceKind(StrEnum):
    PERIODIC = "periodic"
    SOURCE = "source"
    MEASUREMENT = "measurement"
    EVENT = "event"
    ONE_SHOT = "one_shot"
    ALGORITHM_OUTPUT = "algorithm_output"


@dataclass(frozen=True, slots=True)
class LogCadenceDefinition:
    kind: LogCadenceKind
    source: str = ""
    display_names: dict[str, str] = field(default_factory=dict)

    def DisplayName_Get(self, language: str) -> str:
        return self.display_names.get(language, "")


@dataclass(frozen=True, slots=True)
class LogRecordDefinition:
    record: str
    name: str
    record_id: str
    version: int
    payload_size: int
    default_stream: LogStreamConfig
    level: LogPolicyLevel
    purpose: LogPurpose
    capabilities_required: tuple[str, ...] = ()
    recordable_capabilities_required: tuple[str, ...] = ()
    components_required: tuple[str, ...] = ()
    strategy_slots_required: tuple[str, ...] = ()
    display_names: dict[str, str] = field(default_factory=dict)
    cadence: LogCadenceDefinition = field(
        default_factory=lambda: LogCadenceDefinition(LogCadenceKind.SOURCE)
    )
    producer_components: tuple[str, ...] = ()

    def DisplayName_Get(self, language: str) -> str:
        return self.display_names.get(language, self.name).replace("_", " ")


@dataclass(frozen=True, slots=True)
class LogAvailability:
    available: bool
    reason_code: str = ""
    missing: tuple[str, ...] = ()


def _StringTuple_Get(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and bool(item) for item in value
    ):
        raise LogMetadataError(f"{field_name} must be an array of strings")
    return tuple(value)


def _CadenceFallback_Get(policy: str) -> LogCadenceDefinition:
    kind_by_policy = {
        "PERIODIC": LogCadenceKind.PERIODIC,
        "DECIMATION": LogCadenceKind.SOURCE,
        "EVERY": LogCadenceKind.MEASUREMENT,
        "EVENT": LogCadenceKind.EVENT,
        "ONE_SHOT": LogCadenceKind.ONE_SHOT,
    }
    try:
        return LogCadenceDefinition(kind_by_policy[policy.upper()])
    except KeyError as error:
        raise LogMetadataError(f"Unsupported logging policy: {policy}") from error


def _Cadence_Parse(
    value: Any, *, record: str, policy: str
) -> LogCadenceDefinition:
    if value is None:
        return _CadenceFallback_Get(policy)
    if not isinstance(value, dict) or set(value) - {
        "kind",
        "source",
        "display_names",
    }:
        raise LogMetadataError(f"FCCG cadence for {record} must be an object")
    try:
        kind = LogCadenceKind(value.get("kind"))
    except (TypeError, ValueError) as error:
        raise LogMetadataError(f"FCCG cadence kind for {record} is invalid") from error
    source = value.get("source", "")
    if not isinstance(source, str):
        raise LogMetadataError(f"FCCG cadence source for {record} is invalid")
    display_names = value.get("display_names", {})
    if not isinstance(display_names, dict) or not all(
        language in {"zh_CN", "en_US"}
        and isinstance(display_name, str)
        and bool(display_name.strip())
        for language, display_name in display_names.items()
    ):
        raise LogMetadataError(f"FCCG cadence display names for {record} are invalid")
    if kind == LogCadenceKind.PERIODIC and source:
        raise LogMetadataError(f"Periodic cadence for {record} cannot name a source")
    return LogCadenceDefinition(kind, source, dict(display_names))


def ProtocolLogMetadataPath_Get(manifest: PluginManifest) -> Path:
    if manifest.protocol is None:
        raise LogMetadataError(
            f"Protocol plugin {manifest.component_id} has no logging metadata"
        )
    path = manifest.payload_root.joinpath(
        *manifest.protocol.logging_metadata.split("/")
    ).resolve()
    try:
        path.relative_to(manifest.payload_root.resolve())
    except ValueError as error:
        raise LogMetadataError("Protocol logging metadata leaves its payload") from error
    if not path.is_file() or path.is_symlink():
        raise LogMetadataError(f"Protocol logging metadata is unsafe: {path}")
    return path


def ProtocolLogDefinitions_Load(path: Path) -> tuple[LogRecordDefinition, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LogMetadataError(f"Cannot read logging metadata: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise LogMetadataError("Logging metadata must contain a records array")
    fccg = data.get("fccg", {})
    if not isinstance(fccg, dict):
        raise LogMetadataError("Logging metadata fccg block must be an object")
    record_policies = fccg.get("records", {})
    if not isinstance(record_policies, dict):
        raise LogMetadataError("Logging metadata fccg.records must be an object")

    definitions: list[LogRecordDefinition] = []
    seen: set[str] = set()
    for index, entry in enumerate(data["records"]):
        if not isinstance(entry, dict):
            raise LogMetadataError(f"Logging record {index} must be an object")
        record = entry.get("enum")
        name = entry.get("name")
        record_id = entry.get("id")
        version = entry.get("version")
        payload_size = entry.get("payload_size")
        stream = entry.get("default_stream")
        if (
            not isinstance(record, str)
            or not record.startswith("FLIGHT_LOG_RECORD_")
            or record in seen
            or not isinstance(name, str)
            or not isinstance(record_id, str)
            or isinstance(version, bool)
            or not isinstance(version, int)
            or isinstance(payload_size, bool)
            or not isinstance(payload_size, int)
            or not isinstance(stream, dict)
        ):
            raise LogMetadataError(f"Logging record {index} is invalid")
        enabled = stream.get("enabled")
        policy = stream.get("policy")
        decimation = stream.get("decimation", 1)
        period_us = stream.get("period_us", 0)
        if (
            not isinstance(enabled, bool)
            or not isinstance(policy, str)
            or isinstance(decimation, bool)
            or not isinstance(decimation, int)
            or decimation < 1
            or isinstance(period_us, bool)
            or not isinstance(period_us, int)
            or period_us < 0
        ):
            raise LogMetadataError(f"Default stream for {record} is invalid")
        policy_data = record_policies.get(record, {})
        if not isinstance(policy_data, dict) or set(policy_data) - {
            "level",
            "purpose",
            "requires",
            "display_names",
            "cadence",
            "producer_components",
            "default_enabled",
        }:
            raise LogMetadataError(f"FCCG policy for {record} must be an object")
        default_enabled = policy_data.get("default_enabled", enabled)
        if not isinstance(default_enabled, bool):
            raise LogMetadataError(
                f"FCCG default enabled state for {record} is invalid"
            )
        fallback_level = "recommended" if enabled else "optional"
        try:
            level = LogPolicyLevel(policy_data.get("level", fallback_level))
        except ValueError as error:
            raise LogMetadataError(f"FCCG policy level for {record} is invalid") from error
        try:
            purpose = LogPurpose(policy_data["purpose"])
        except (KeyError, TypeError, ValueError) as error:
            raise LogMetadataError(
                f"FCCG purpose for {record} must be flight or test"
            ) from error
        requirements = policy_data.get("requires", {})
        if not isinstance(requirements, dict) or set(requirements) - {
            "capabilities",
            "recordable_capabilities",
            "components",
            "strategy_slots",
        }:
            raise LogMetadataError(f"FCCG requirements for {record} are invalid")
        display_names = policy_data.get("display_names", {})
        if not isinstance(display_names, dict) or not all(
            language in {"zh_CN", "en_US"}
            and isinstance(display_name, str)
            and bool(display_name.strip())
            for language, display_name in display_names.items()
        ):
            raise LogMetadataError(f"FCCG display names for {record} are invalid")
        definitions.append(
            LogRecordDefinition(
                record=record,
                name=name,
                record_id=record_id,
                version=version,
                payload_size=payload_size,
                default_stream=LogStreamConfig(
                    record,
                    default_enabled,
                    policy.upper(),
                    decimation,
                    period_us,
                ),
                level=level,
                purpose=purpose,
                capabilities_required=_StringTuple_Get(
                    requirements.get("capabilities"),
                    f"{record}.requires.capabilities",
                ),
                recordable_capabilities_required=_StringTuple_Get(
                    requirements.get("recordable_capabilities"),
                    f"{record}.requires.recordable_capabilities",
                ),
                components_required=_StringTuple_Get(
                    requirements.get("components"),
                    f"{record}.requires.components",
                ),
                strategy_slots_required=_StringTuple_Get(
                    requirements.get("strategy_slots"),
                    f"{record}.requires.strategy_slots",
                ),
                display_names=dict(display_names),
                cadence=_Cadence_Parse(
                    policy_data.get("cadence"),
                    record=record,
                    policy=policy,
                ),
                producer_components=_StringTuple_Get(
                    policy_data.get("producer_components"),
                    f"{record}.producer_components",
                ),
            )
        )
        seen.add(record)
    if not definitions:
        raise LogMetadataError("Logging metadata declares no records")
    unknown_policies = set(record_policies) - seen
    if unknown_policies:
        raise LogMetadataError(
            "FCCG policy references unknown records: "
            + ", ".join(sorted(unknown_policies))
        )
    return tuple(definitions)


def ProtocolLogDefinitions_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[LogRecordDefinition, ...]:
    if model.protocols.get("logging") is None:
        return ()
    return ProtocolLogDefinitions_Load(
        ProjectProtocolLogMetadataPath_Get(model, catalog)
    )


def ProjectProtocolLogMetadataPath_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> Path:
    selection = model.protocols.get("logging")
    if selection is None:
        raise LogMetadataError("Exactly one Logging Protocol must be selected")
    manifest = catalog.Component_Get(selection.component)
    selected_id = selection.profile
    if manifest.protocol is not None:
        matches = tuple(
            profile
            for profile in manifest.protocol.profiles.get("logging", ())
            if profile.profile_id == selected_id
        )
        if len(matches) == 1:
            path = manifest.payload_root.joinpath(
                *matches[0].decoder_metadata.split("/")
            ).resolve()
            try:
                path.relative_to(manifest.payload_root.resolve())
            except ValueError as error:
                raise LogMetadataError(
                    "Protocol profile decoder metadata leaves its payload"
                ) from error
            if path.is_file() and not path.is_symlink():
                return path
            raise LogMetadataError(
                f"Protocol profile decoder metadata is unsafe: {path}"
            )
    return ProtocolLogMetadataPath_Get(manifest)


def ProjectCapabilities_Get(model: ProjectModel, catalog: PluginCatalog) -> set[str]:
    capabilities: set[str] = set()
    device_plugins = set(model.DevicePluginIds_Get())
    for component_id in model.ComponentIds_Get():
        if component_id in device_plugins:
            continue
        try:
            capabilities.update(catalog.Component_Get(component_id).provides)
        except FccgError:
            continue
    resolution = CapabilityResolution_Resolve(model, catalog)
    for enabled in resolution.enabled_by_instance.values():
        capabilities.update(enabled)
    return capabilities


def ProjectRecordableOutputs_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[set[str], dict[str, str]]:
    """Return enabled raw outputs and explicit device-output disable reasons."""
    enabled: set[str] = set()
    disabled_reasons: dict[str, str] = {}
    for instance in model.device_instances:
        manifest = catalog.Component_Get(instance.plugin)
        values = manifest.metadata.get("recordable_outputs", {})
        if not isinstance(values, dict):
            continue
        for capability, configuration in values.items():
            if not isinstance(capability, str) or not isinstance(configuration, dict):
                continue
            if configuration.get("enabled") is True:
                enabled.add(capability)
                disabled_reasons.pop(capability, None)
            elif capability not in enabled:
                reason_code = configuration.get("reason_code", "")
                if isinstance(reason_code, str) and reason_code:
                    disabled_reasons[capability] = reason_code
    return enabled, disabled_reasons


def ProjectLogProducers_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> set[str]:
    """Return selected components and their declarative producer identities."""
    producers = set(model.ComponentIds_Get())
    for component_id in model.ComponentIds_Get():
        try:
            manifest = catalog.Component_Get(component_id)
        except FccgError:
            continue
        declared = manifest.metadata.get("log_producers", ())
        if isinstance(declared, list):
            producers.update(
                item for item in declared if isinstance(item, str) and item
            )
        protocol_declared = manifest.metadata.get(
            "protocol_log_producers", {}
        )
        if isinstance(protocol_declared, dict):
            for category, identities in protocol_declared.items():
                if model.protocols.get(str(category)) is None:
                    continue
                if isinstance(identities, list):
                    producers.update(
                        item
                        for item in identities
                        if isinstance(item, str) and item
                    )
    return producers


def LogAvailability_Get(
    definition: LogRecordDefinition,
    model: ProjectModel,
    catalog: PluginCatalog,
) -> LogAvailability:
    selected = set(model.ComponentIds_Get())
    capabilities = ProjectCapabilities_Get(model, catalog)
    recordable, disabled_recordable = ProjectRecordableOutputs_Get(model, catalog)
    missing_capabilities = tuple(
        value for value in definition.capabilities_required if value not in capabilities
    )
    if missing_capabilities:
        return LogAvailability(
            False, "logging.unavailable.capability", missing_capabilities
        )
    missing_recordable = tuple(
        value
        for value in definition.recordable_capabilities_required
        if value not in recordable
    )
    if missing_recordable:
        reason_codes = tuple(
            dict.fromkeys(
                disabled_recordable.get(value, "")
                for value in missing_recordable
                if disabled_recordable.get(value, "")
            )
        )
        return LogAvailability(
            False,
            (
                reason_codes[0]
                if len(reason_codes) == 1
                else "logging.unavailable.recordable"
            ),
            missing_recordable,
        )
    missing_components = tuple(
        value for value in definition.components_required if value not in selected
    )
    if missing_components:
        return LogAvailability(
            False, "logging.unavailable.component", missing_components
        )
    missing_slots = tuple(
        value
        for value in definition.strategy_slots_required
        if not model.strategies.get(value)
    )
    if missing_slots:
        return LogAvailability(False, "logging.unavailable.strategy", missing_slots)
    if definition.producer_components:
        producers = ProjectLogProducers_Get(model, catalog)
        if not any(
            producer in producers for producer in definition.producer_components
        ):
            return LogAvailability(
                False,
                "logging.unavailable.producer",
                definition.producer_components,
            )
    return LogAvailability(True)


def LoggingProfile_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[LogRecordDefinition, ...]:
    if model.protocols.get("logging") is None:
        # Keep the user's stream choices as inactive configuration.  Restoring
        # a compatible Logging Protocol reconciles known records against this
        # retained state without treating it as an active logging contract.
        return ()
    definitions = ProtocolLogDefinitions_Get(model, catalog)
    current = {stream.record: stream for stream in model.logging_streams}
    reconciled: list[LogStreamConfig] = []
    for definition in definitions:
        stream = current.get(definition.record, definition.default_stream)
        availability = LogAvailability_Get(definition, model, catalog)
        enabled = stream.enabled
        if not availability.available:
            enabled = False
        elif definition.level == LogPolicyLevel.REQUIRED:
            enabled = True
        reconciled.append(
            LogStreamConfig(
                record=definition.record,
                enabled=enabled,
                policy=definition.default_stream.policy,
                decimation=(1 if definition.default_stream.policy == "EVERY" else stream.decimation),
                period_us=(0 if definition.default_stream.policy == "EVERY" else stream.period_us),
            )
        )
    model.logging_streams = reconciled
    return definitions


def LoggingProfile_AvailabilityTransitionApply(
    previous_model: ProjectModel,
    model: ProjectModel,
    catalog: PluginCatalog,
) -> tuple[LogRecordDefinition, ...]:
    """Restore metadata defaults only for records newly available after a change."""
    definitions = LoggingProfile_Reconcile(model, catalog)
    if not definitions:
        if previous_model.protocols.get("logging") is not None:
            model.logging_streams = [
                replace(stream, enabled=False) for stream in model.logging_streams
            ]
        return definitions
    previous_definitions = {
        definition.record: definition
        for definition in ProtocolLogDefinitions_Get(previous_model, catalog)
    }
    current = {stream.record: stream for stream in model.logging_streams}
    reconciled: list[LogStreamConfig] = []
    for definition in definitions:
        stream = current[definition.record]
        available = LogAvailability_Get(definition, model, catalog).available
        previous_definition = previous_definitions.get(definition.record)
        previously_available = (
            previous_definition is not None
            and LogAvailability_Get(
                previous_definition, previous_model, catalog
            ).available
        )
        enabled = stream.enabled
        if not available:
            enabled = False
        elif definition.level == LogPolicyLevel.REQUIRED:
            enabled = True
        elif not previously_available:
            enabled = definition.default_stream.enabled
        reconciled.append(replace(stream, enabled=enabled))
    model.logging_streams = reconciled
    return definitions


def LoggingProfile_SelectAllAvailable(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[LogRecordDefinition, ...]:
    """Enable every Record supported by the reconciled project composition."""
    if model.protocols.get("logging") is None:
        return ()
    definitions = LoggingProfile_Reconcile(model, catalog)
    current = {stream.record: stream for stream in model.logging_streams}
    model.logging_streams = [
        LogStreamConfig(
            record=definition.record,
            enabled=LogAvailability_Get(definition, model, catalog).available,
            policy=current[definition.record].policy,
            decimation=current[definition.record].decimation,
            period_us=current[definition.record].period_us,
        )
        for definition in definitions
    ]
    return definitions
