from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any


def _Immutable_Get(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _Immutable_Get(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_Immutable_Get(item) for item in value)
    return value


def _JsonCompatible_Get(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _JsonCompatible_Get(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_JsonCompatible_Get(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class DecoderPackageIdentity:
    package_sha256: str
    generation_profile_sha256: str
    generation_profile_hash_128: str
    record_catalog_sha256: str
    project_semantics_sha256: str
    package_schema_id: str
    package_schema_major: int
    package_schema_minor: int
    declared_container_id: str
    container_version_range: str
    project_name: str
    firmware_version: str
    firmware_commit: str

    def ToDict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CalibrationSnapshot:
    timestamp_us: int
    selection_boundary_us: int
    selection_boundary_kind: str
    source_id: int
    virtual_imu_id: int
    mode: int
    state: int
    ready: bool
    completed_face_mask: int
    samples: int
    reject_count: int
    retry_count: int
    start_sequence: int
    accel_bias_mps2: tuple[float, float, float]
    accel_scale: tuple[float, float, float]
    gyro_bias_radps: tuple[float, float, float]
    gyro_scale: tuple[float, float, float]
    corrected_sample_count: int
    correction_valid: bool

    @property
    def mode_name(self) -> str:
        return {
            0: "NONE",
            1: "ONE_FACE",
            2: "SIX_FACE",
        }.get(self.mode, f"UNKNOWN_{self.mode}")

    @property
    def identity_model(self) -> bool:
        return self.mode == 0

    def ToDict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode_name"] = self.mode_name
        payload["identity_model"] = self.identity_model
        return payload


@dataclass(frozen=True, slots=True)
class DatasetSemanticContext:
    package_identity: DecoderPackageIdentity
    firmware_algorithm_ids: tuple[str, ...]
    protocols: Mapping[str, Any]
    hardware: Mapping[str, Any]
    modes: Mapping[str, Any]
    strategies: Mapping[str, Any]
    devices: tuple[Mapping[str, Any], ...]
    device_descriptors: tuple[Mapping[str, Any], ...]
    capability_endpoints: tuple[Mapping[str, Any], ...]
    capability_routes: tuple[Mapping[str, Any], ...]
    canonical_channels: tuple[Mapping[str, Any], ...]
    record_views: tuple[Mapping[str, Any], ...]
    event_catalog: Mapping[str, Any]
    logging_streams: tuple[Mapping[str, Any], ...]
    components: tuple[Mapping[str, Any], ...]
    component_locks: tuple[Mapping[str, Any], ...]
    raw_channel_id_templates: Mapping[str, Any]
    stable_aliases: Mapping[str, str]
    calibration: CalibrationSnapshot
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocols", _Immutable_Get(self.protocols))
        object.__setattr__(self, "hardware", _Immutable_Get(self.hardware))
        object.__setattr__(self, "modes", _Immutable_Get(self.modes))
        object.__setattr__(self, "strategies", _Immutable_Get(self.strategies))
        for field_name in (
            "devices",
            "device_descriptors",
            "capability_endpoints",
            "capability_routes",
            "canonical_channels",
            "record_views",
            "logging_streams",
            "components",
            "component_locks",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(_Immutable_Get(item) for item in getattr(self, field_name)),
            )
        object.__setattr__(self, "event_catalog", _Immutable_Get(self.event_catalog))
        object.__setattr__(
            self,
            "raw_channel_id_templates",
            _Immutable_Get(self.raw_channel_id_templates),
        )
        object.__setattr__(self, "stable_aliases", _Immutable_Get(self.stable_aliases))
        object.__setattr__(self, "raw_metadata", _Immutable_Get(self.raw_metadata))

    def FirmwareParameters_Get(self, component_id: str) -> Mapping[str, Any] | None:
        for group in self.raw_metadata.get("firmware_algorithm_parameters", ()):
            if group["component"] == component_id:
                return MappingProxyType({p["id"]: p for p in group["parameters"]})
        return None

    def FirmwareParameterSets_Get(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.raw_metadata.get("firmware_algorithm_parameters", ()))

    def StableChannelId_Get(self, role_id: str) -> str | None:
        return self.stable_aliases.get(role_id)

    def Project_Get(self) -> str:
        return self.package_identity.project_name

    def FirmwareVersion_Get(self) -> str:
        return self.package_identity.firmware_version

    def FirmwareAlgorithms_Get(self) -> tuple[str, ...]:
        return self.firmware_algorithm_ids

    def Strategies_Get(self) -> Mapping[str, Any]:
        return self.strategies

    def Modes_Get(self) -> Mapping[str, Any]:
        return self.modes

    def PhysicalDevices_Get(self) -> tuple[Mapping[str, Any], ...]:
        return self.devices

    def CapabilityEndpoint_Get(
        self,
        descriptor_id: int,
    ) -> Mapping[str, Any] | None:
        return next(
            (
                endpoint
                for endpoint in self.capability_endpoints
                if endpoint.get("descriptor_id") == descriptor_id
            ),
            None,
        )

    def CanonicalRoute_Get(self, channel_id: str) -> Mapping[str, Any] | None:
        return next(
            (
                channel
                for channel in self.canonical_channels
                if channel.get("channel_id") == channel_id
            ),
            None,
        )

    def RecordView_Get(self, record_name: str) -> Mapping[str, Any] | None:
        normalized = record_name.removeprefix("FLIGHT_LOG_RECORD_").upper()
        return next(
            (
                view
                for view in self.record_views
                if str(view.get("record", ""))
                .removeprefix("FLIGHT_LOG_RECORD_")
                .upper()
                == normalized
            ),
            None,
        )

    def EventDefinition_Get(self, event_key: str) -> Any:
        return self.event_catalog.get(event_key)

    def LoggingStream_Get(self, record_name: str) -> Mapping[str, Any] | None:
        normalized = record_name.removeprefix("FLIGHT_LOG_RECORD_").upper()
        return next(
            (
                stream
                for stream in self.logging_streams
                if str(stream.get("record", ""))
                .removeprefix("FLIGHT_LOG_RECORD_")
                .upper()
                == normalized
            ),
            None,
        )

    def PackageIdentity_Get(self) -> DecoderPackageIdentity:
        return self.package_identity

    def StableRole_Get(self, role_id: str) -> str | None:
        return self.StableChannelId_Get(role_id)

    def FirmwareAlgorithm_IsMember(self, component_id: str) -> bool:
        return component_id in self.firmware_algorithm_ids

    def Protocol_Get(self, protocol_name: str) -> Any:
        return self.protocols.get(protocol_name)

    def CapabilityRoutes_Get(self, capability: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            route
            for route in self.capability_routes
            if route.get("capability") == capability
        )

    def ToDict(self) -> dict[str, Any]:
        return {
            "package_identity": self.package_identity.ToDict(),
            "firmware_algorithm_ids": list(self.firmware_algorithm_ids),
            "algorithm_parameters": _JsonCompatible_Get(self.FirmwareParameterSets_Get()),
            "protocols": _JsonCompatible_Get(self.protocols),
            "hardware": _JsonCompatible_Get(self.hardware),
            "modes": _JsonCompatible_Get(self.modes),
            "strategies": _JsonCompatible_Get(self.strategies),
            "devices": _JsonCompatible_Get(self.devices),
            "device_descriptors": _JsonCompatible_Get(self.device_descriptors),
            "capability_endpoints": _JsonCompatible_Get(self.capability_endpoints),
            "capability_routes": _JsonCompatible_Get(self.capability_routes),
            "canonical_channels": _JsonCompatible_Get(self.canonical_channels),
            "record_views": _JsonCompatible_Get(self.record_views),
            "event_catalog": _JsonCompatible_Get(self.event_catalog),
            "logging_streams": _JsonCompatible_Get(self.logging_streams),
            "components": _JsonCompatible_Get(self.components),
            "component_locks": _JsonCompatible_Get(self.component_locks),
            "raw_channel_id_templates": _JsonCompatible_Get(self.raw_channel_id_templates),
            "stable_aliases": dict(self.stable_aliases),
            "calibration": self.calibration.ToDict(),
        }
