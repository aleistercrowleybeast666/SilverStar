from __future__ import annotations

import hashlib
import json
import stat
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.cli import _Algorithm_Resolve
from silverstar_flp.cli import main as Cli_Main
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.decoder_profiles import (
    DecoderProfileCache,
    DecoderProfileDescriptor,
    DecoderProfileError,
    DecoderProfileMatcher,
    DecoderProfilePackage,
    DecoderProfileParserPlugin,
    ProjectSemantics,
    RecordCatalog,
    TaskDirectoryScanner,
)
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.log_open import (
    LogOpenCoordinator,
    LogOpenRequest,
    LogOpenSourceMode,
)
from silverstar_flp.plugins.api.log_container import (
    LogContainerMetadata,
    LogContainerPlugin,
    ParseOptions,
    ProbeResult,
)
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.plugins.log_containers.sslog0.plugin import Sslog0ContainerPlugin
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import (
    START_TIMESTAMP_US,
    Event_Payload,
    SyntheticSslogBuilder,
)

IMU_RECORD_TYPE = 0x40
DESCRIPTOR_RECORD_TYPE = 0x1D


def _JsonBytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _CatalogDocument_Build(*, payload_size: int = 28) -> dict[str, Any]:
    return {
        "catalog_schema_id": "silverstar.sslog.record-catalog/1.0",
        "endianness": "little",
        "field_contract": {
            "defaults": {
                "unit": "1",
                "quantity": "dimensionless",
                "scale": 1,
                "offset": 0,
                "enum": None,
                "bitfield": None,
                "timestamp": False,
                "validity": None,
            },
            "semantic_rules": [
                {
                    "suffix": "_timestamp_us",
                    "unit": "us",
                    "quantity": "monotonic_time",
                    "timestamp": True,
                },
                {
                    "suffix": "_mps2",
                    "unit": "m/s^2",
                    "quantity": "acceleration",
                },
            ],
        },
        "records": [
            {
                "id": f"0x{IMU_RECORD_TYPE:02X}",
                "version": 0,
                "name": "IMU_NATIVE",
                "payload_size": payload_size,
                "fields": [
                    {"name": "source_descriptor_id", "type": "u16"},
                    {"name": "instance_id", "type": "u8"},
                    {"type": "pad", "count": 1},
                    {"name": "sample_timestamp_us", "type": "u64"},
                    {"name": "accel_b_mps2", "type": "f32", "count": 3},
                    {
                        "name": "valid_mask",
                        "type": "u32",
                        "bitfield": [{"mask": "0x1", "name": "ACCEL_VALID"}],
                    },
                ],
            },
            {
                "id": f"0x{DESCRIPTOR_RECORD_TYPE:02X}",
                "version": 0,
                "name": "DECODER_PROFILE_DESCRIPTOR",
                "payload_size": 64,
                "fields": [
                    {"name": "package_schema_major", "type": "u16"},
                    {"name": "package_schema_minor", "type": "u16"},
                    {"name": "container_format_major", "type": "u16"},
                    {"name": "container_format_minor", "type": "u16"},
                    {"name": "record_catalog_hash_128", "type": "u8", "count": 16},
                    {
                        "name": "project_semantics_hash_128",
                        "type": "u8",
                        "count": 16,
                    },
                    {
                        "name": "generation_profile_hash_128",
                        "type": "u8",
                        "count": 16,
                    },
                    {"type": "pad", "count": 8},
                ],
            },
            {
                "id": "0x02",
                "version": 0,
                "name": "EVENT",
                "payload_size": 12,
                "fields": [
                    {"name": "event_id", "type": "u16"},
                    {"name": "category", "type": "u16"},
                    {"name": "arg0", "type": "u32"},
                    {"name": "arg1", "type": "u32"},
                ],
            },
            {
                "id": "0x17",
                "version": 0,
                "name": "CALIBRATION_RESULT",
                "payload_size": 72,
                "fields": [
                    {"name": "source_id", "type": "u16"},
                    {"name": "virtual_imu_id", "type": "u16"},
                    {"name": "mode", "type": "u8"},
                    {"name": "state", "type": "u8"},
                    {"name": "ready", "type": "u8"},
                    {"name": "completed_face_mask", "type": "u8"},
                    {"name": "samples", "type": "u32"},
                    {"name": "reject_count", "type": "u32"},
                    {"name": "retry_count", "type": "u32"},
                    {"name": "start_sequence", "type": "u32"},
                    {"name": "accel_bias_mps2", "type": "f32", "count": 3},
                    {"name": "accel_scale", "type": "f32", "count": 3},
                    {"name": "gyro_bias_radps", "type": "f32", "count": 3},
                    {"name": "gyro_scale", "type": "f32", "count": 3},
                ],
            },
        ],
    }


def _SemanticsDocument_Build() -> dict[str, Any]:
    device_descriptors = [
        {
            "descriptor_id": 1,
            "physical_device_id": 10,
            "device_class": "SYSTEM_DEVICE_CLASS_IMU",
            "instance_id": 0,
            "source_component": "silverstar.device.imu.alpha",
            "source_instance_id": "imu0",
        },
        {
            "descriptor_id": 2,
            "physical_device_id": 20,
            "device_class": "SYSTEM_DEVICE_CLASS_IMU",
            "instance_id": 1,
            "source_component": "silverstar.device.imu.beta",
            "source_instance_id": "imu1",
        },
    ]
    capability_endpoints = [
        {
            **descriptor,
            "device_class": "imu",
            "plugin": descriptor["source_component"],
            "model": "Alpha IMU" if index == 0 else "Beta IMU",
            "capabilities": ["imu.acceleration"],
        }
        for index, descriptor in enumerate(device_descriptors)
    ]
    return {
        "schema_id": "silverstar.project-semantics/1.2",
        "schema_version": 0x00010002,
        "project": "SYNTHETIC_DUAL_IMU",
        "firmware_version": "0.0.test",
        "device_descriptors": device_descriptors,
        "capability_endpoints": capability_endpoints,
        "physical_devices": [
            {
                "instance_id": f"imu{index}",
                "physical_device_id": descriptor["physical_device_id"],
                "descriptor_ids": [descriptor["descriptor_id"]],
                "plugin": descriptor["source_component"],
                "model": "Alpha IMU" if index == 0 else "Beta IMU",
                "capabilities": ["imu.acceleration"],
            }
            for index, descriptor in enumerate(device_descriptors)
        ],
        "record_views": [
            {
                "record": "FLIGHT_LOG_RECORD_IMU_NATIVE",
                "record_type": f"0x{IMU_RECORD_TYPE:02X}",
                "record_version": 0,
                "payload_size": 28,
                "partition_by": ["source_descriptor_id", "instance_id"],
                "columns": ["accel_b_mps2"],
                "validity": {
                    "field": "valid_mask",
                    "masks": {"accel_b_mps2": 1},
                },
            }
        ],
        "raw_channel_id_templates": {
            "default": "{record}:{source_descriptor_id}:{instance_id}",
            "partition_by": [
                "source_descriptor_id",
                "instance_id",
                "physical_device_id",
            ],
        },
        "canonical_channels": [
            {
                "channel_id": "canonical:imu.acceleration",
                "capability": "imu.acceleration",
                "endpoint_descriptor_ids": [1],
                "automatic": True,
            }
        ],
        "event_catalog": {
            "mission_start": {
                "event_id": 3,
                "name": "MISSION_START",
                "arg0": "synthetic typed argument",
            }
        },
        "algorithms": ["silverstar.algorithm.estimator.kf6"],
        "firmware_algorithm_parameters": [],
        "logging_streams": [{"record": "FLIGHT_LOG_RECORD_IMU_NATIVE", "enabled": True}],
        "protocols": {
            "logging": {"profile": "flight_log.0_0"},
            "maintenance": None,
            "telemetry": None,
        },
        "modes": {"calibration": []},
    }


def _FccgSemanticsDocument_Build() -> dict[str, Any]:
    return _SemanticsDocument_Build()


def _PackageFiles_Build(
    *,
    catalog_document: dict[str, Any] | None = None,
    semantics_document: dict[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, str]]:
    catalog_bytes = _JsonBytes(catalog_document or _CatalogDocument_Build())
    semantics_bytes = _JsonBytes(semantics_document or _SemanticsDocument_Build())
    catalog_hash = hashlib.sha256(catalog_bytes).hexdigest()
    semantics_hash = hashlib.sha256(semantics_bytes).hexdigest()
    schema_id = "silverstar.ssdecoder.package-schema/1.2"
    container_id = "silverstar.sslog.container/0.0"
    generation_hash = hashlib.sha256(
        schema_id.encode("utf-8")
        + b"\n"
        + container_id.encode("utf-8")
        + b"\n"
        + bytes.fromhex(catalog_hash)
        + bytes.fromhex(semantics_hash)
    ).hexdigest()
    member_names = [
        "manifest.json",
        "record_catalog.json",
        "project_semantics.json",
        "checksums.sha256",
        "README.md",
    ]
    manifest = {
        "format": "SilverStar.ssdecoder",
        "contains_executable_code": False,
        "package_schema": {
            "id": schema_id,
            "major": 1,
            "minor": 2,
        },
        "display_name": "Synthetic dual IMU decoder",
        "project_name": "SYNTHETIC_DUAL_IMU",
        "firmware_version": "0.0.test",
        "required_flp_minimum_version": "0.0.1",
        "supported_primitive_types": ["f32", "pad", "u8", "u16", "u32", "u64"],
        "selected_log_format_profile": "flight_log.0_0",
        "entries": member_names,
        "container_plugin": {
            "id": container_id,
            "version_range": {
                "minimum_inclusive": "0.0",
                "maximum_inclusive": "0.0",
            },
            "api_version": 1,
        },
        "record_catalog_sha256": catalog_hash,
        "project_semantics_sha256": semantics_hash,
        "generation_profile_sha256": generation_hash,
    }
    files = {
        "manifest.json": _JsonBytes(manifest),
        "record_catalog.json": catalog_bytes,
        "project_semantics.json": semantics_bytes,
        "README.md": b"# Synthetic decoder fixture\n",
    }
    checksum_text = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
    )
    files["checksums.sha256"] = checksum_text.encode()
    return files, {
        "catalog": catalog_hash,
        "semantics": semantics_hash,
        "generation": generation_hash,
    }


def _Package_Write(
    path: Path,
    *,
    files: dict[str, bytes] | None = None,
) -> tuple[Path, dict[str, str]]:
    package_files, hashes = _PackageFiles_Build() if files is None else (files, {})
    if files is not None:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
        hashes = {
            "catalog": manifest.get(
                "record_catalog_sha256",
                manifest.get("record_catalog_hash", ""),
            ),
            "semantics": manifest.get("project_semantics_sha256", ""),
            "generation": manifest.get("generation_profile_sha256", ""),
        }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in package_files.items():
            archive.writestr(name, content)
    return path, hashes


def _ImuPayload_Build(
    descriptor_id: int,
    instance_id: int,
    timestamp_us: int,
    values: tuple[float, float, float],
) -> bytes:
    return struct.pack(
        "<HBxQ3fI",
        descriptor_id,
        instance_id,
        timestamp_us,
        *values,
        1,
    )


def _DescriptorPayload_Build(hashes: dict[str, str]) -> bytes:
    return (
        struct.pack("<4H", 1, 2, 0, 0)
        + bytes.fromhex(hashes["catalog"][:32])
        + bytes.fromhex(hashes["semantics"][:32])
        + bytes.fromhex(hashes["generation"][:32])
        + bytes(8)
    )


def _CalibrationPayload_Build(
    *,
    mode: int,
    completed_face_mask: int,
    samples: int,
    state: int = 4,
    ready: int = 1,
    start_sequence: int = 0,
) -> bytes:
    calibrated = mode != 0
    return struct.pack(
        "<HH4B4I12f",
        1,
        1,
        mode,
        state,
        ready,
        completed_face_mask,
        samples,
        0,
        0,
        start_sequence,
        *((0.1, -0.2, 0.3) if calibrated else (0.0, 0.0, 0.0)),
        *((1.01, 0.99, 1.02) if calibrated else (1.0, 1.0, 1.0)),
        *((0.001, -0.002, 0.003) if calibrated else (0.0, 0.0, 0.0)),
        *((1.001, 0.999, 1.002) if calibrated else (1.0, 1.0, 1.0)),
    )


def _CalibrationNonePayload_Build(
    *,
    samples: int = 0,
    ready: int = 1,
    start_sequence: int = 0,
) -> bytes:
    return _CalibrationPayload_Build(
        mode=0,
        completed_face_mask=0,
        samples=samples,
        ready=ready,
        start_sequence=start_sequence,
    )


def _ContainerMap_Get() -> dict[str, Sslog0ContainerPlugin]:
    plugin = Sslog0ContainerPlugin()
    return {plugin.metadata.plugin_id: plugin}


def _Checksums_Refresh(files: dict[str, bytes]) -> None:
    checksum_text = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
        if name != "checksums.sha256"
    )
    files["checksums.sha256"] = checksum_text.encode()


def test_strict_package_drives_dual_imu_channel_partitioning(tmp_path: Path) -> None:
    package_path, hashes = _Package_Write(tmp_path / "dual_imu.ssdecoder")
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US, (1.0, 2.0, 3.0)),
        START_TIMESTAMP_US,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(2, 1, START_TIMESTAMP_US + 10, (4.0, 5.0, 6.0)),
        START_TIMESTAMP_US + 10,
    )
    log_path = builder.File_Write(tmp_path / "dual_imu.sslog")

    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(log_path)

    assert dataset.metadata["parse_status"] == "complete"
    assert dataset.metadata["decoder_profile_match_mode"] == "exact_generation_profile"
    first_id = "IMU_NATIVE:1:0.accel_b_mps2"
    second_id = "IMU_NATIVE:2:1.accel_b_mps2"
    assert set(dataset.series) == {first_id, second_id}
    assert dataset.series[first_id].values.tolist() == [[1.0, 2.0, 3.0]]
    assert dataset.series[second_id].values.tolist() == [[4.0, 5.0, 6.0]]
    assert dataset.series[first_id].metadata["physical_device_id"] == 10
    assert dataset.series[second_id].metadata["model"] == "Beta IMU"


def test_firmware_container_id_alias_keeps_builtin_id_and_hash_contract(
    tmp_path: Path,
) -> None:
    files, hashes = _PackageFiles_Build()
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    schema_id = "silverstar.ssdecoder.package-schema/1.2"
    declared_container_id = "silverstar.sslog.container/0.0"
    generation_hash = hashlib.sha256(
        schema_id.encode("utf-8")
        + b"\n"
        + declared_container_id.encode("utf-8")
        + b"\n"
        + bytes.fromhex(hashes["catalog"])
        + bytes.fromhex(hashes["semantics"])
    ).hexdigest()
    manifest["package_schema"]["id"] = schema_id
    manifest["container_plugin"]["id"] = declared_container_id
    manifest["generation_profile_sha256"] = generation_hash
    manifest["generation_profile_hash_128"] = generation_hash[:32]
    files["manifest.json"] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    package_path, _ = _Package_Write(
        tmp_path / "firmware_container_id.ssdecoder",
        files=files,
    )

    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )

    assert package.declared_container_plugin_id == declared_container_id
    assert package.required_container_plugin_id == "silverstar.flight_log.container.0_0"
    assert package.generation_profile_sha256 == generation_hash


def test_fccg_record_views_bind_to_instance_channels_without_explicit_map(
    tmp_path: Path,
) -> None:
    files, hashes = _PackageFiles_Build(
        semantics_document=_FccgSemanticsDocument_Build()
    )
    package_path, _ = _Package_Write(
        tmp_path / "fccg_views.ssdecoder",
        files=files,
    )
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US, (1.0, 2.0, 3.0)),
        START_TIMESTAMP_US,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(2, 1, START_TIMESTAMP_US + 10, (4.0, 5.0, 6.0)),
        START_TIMESTAMP_US + 10,
    )

    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(builder.File_Write(tmp_path / "fccg_views.sslog"))

    first_id = "IMU_NATIVE:1:0.accel_b_mps2"
    second_id = "IMU_NATIVE:2:1.accel_b_mps2"
    assert set(dataset.series) == {first_id, second_id}
    assert dataset.series[first_id].unit == "m/s^2"
    assert dataset.series[first_id].quantity == "acceleration"
    assert dataset.series[first_id].valid.tolist() == [True]
    assert dataset.series[first_id].metadata["canonical_channel_ids"] == (
        "canonical:imu.acceleration",
    )
    assert dataset.series[first_id].metadata["capabilities"] == (
        "imu.acceleration",
    )
    assert dataset.series[second_id].metadata["physical_device_id"] == 20
    assert package.semantics.canonical_channels[0]["channel_id"] == (
        "canonical:imu.acceleration"
    )


def test_descriptor_hash_selects_exact_package_and_parser_verifies_it(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "exact.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 1, (1.0, 2.0, 3.0)),
        START_TIMESTAMP_US + 1,
    )
    log_path = builder.File_Write(tmp_path / "descriptor.sslog")
    containers = _ContainerMap_Get()

    result = DecoderProfileMatcher(containers).Match(log_path, [package_path])

    assert result.descriptor_found
    assert len(result.matches) == 1
    assert result.matches[0].reason == "exact_generation_profile"
    package = result.matches[0].package
    dataset = DecoderProfileParserPlugin(
        containers[package.required_container_plugin_id],
        package,
    ).parse(log_path)
    assert dataset.metadata["decoder_profile_match_mode"] == "exact_generation_profile"

    wrong_semantics = _SemanticsDocument_Build()
    wrong_semantics["firmware_version"] = "different"
    wrong_files, _ = _PackageFiles_Build(semantics_document=wrong_semantics)
    wrong_path, _ = _Package_Write(tmp_path / "wrong.ssdecoder", files=wrong_files)
    wrong_package = DecoderProfilePackage.Load(
        wrong_path,
        container_plugins=containers,
    )
    wrong_match = DecoderProfileMatcher(containers).Match(log_path, [wrong_path])
    assert wrong_match.descriptor_found
    assert wrong_match.matches == ()
    with pytest.raises(RuntimeError, match="decoder_profile_.*hash_mismatch"):
        DecoderProfileParserPlugin(
            containers[wrong_package.required_container_plugin_id],
            wrong_package,
        ).parse(log_path)


def test_log_open_coordinator_builds_immutable_semantics_and_none_calibration(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "coordinator.ssdecoder")
    source_bytes = package_path.read_bytes()
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 3,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 1, (1.0, 2.0, 3.0)),
        START_TIMESTAMP_US + 1,
    )
    log_path = builder.File_Write(tmp_path / "coordinator.sslog")
    coordinator = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    )

    result = coordinator.Open(
        LogOpenRequest(
            log_path=log_path,
            decoder_package_path=package_path,
        )
    )

    context = result.dataset.semantic_context
    assert context is not None
    assert result.match_mode == "exact_generation_profile"
    assert context.Project_Get() == "SYNTHETIC_DUAL_IMU"
    assert context.FirmwareAlgorithms_Get() == ("silverstar.algorithm.estimator.kf6",)
    assert context.calibration.mode_name == "NONE"
    assert context.calibration.ready
    assert context.calibration.identity_model
    assert context.calibration.samples == 0
    assert context.calibration.accel_bias_mps2 == (0.0, 0.0, 0.0)
    assert context.calibration.accel_scale == (1.0, 1.0, 1.0)
    event = result.dataset.Records_Get("EVENT")[0]
    assert event.payload["event_name"] == "MISSION_START"
    assert event.payload["event_semantics"]["arg0"] == "synthetic typed argument"
    # Generic arbitrary catalog data survives; retired native IMU has no stable alias.
    raw_channel_id = 'IMU_NATIVE:1:0.accel_b_mps2'
    assert context.StableRole_Get('imu.native.accel_b') is None
    assert result.dataset.Series_Get('imu.native.accel_b') is None
    assert not result.dataset.Series_Get(raw_channel_id).values.flags.writeable
    assert package_path.read_bytes() == source_bytes
    assert result.cache_reference.package_sha256 == result.package.package_sha256
    kf6 = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    configuration = kf6.ConfigurationAvailability_Get(result.dataset)
    assert configuration.firmware_member
    assert not configuration.recorded_output_available
    assert not configuration.recorded_available
    assert configuration.offline_available
    assert "p0_position_e" in configuration.missing_recorded_parameters
    export_directory = tmp_path / "audit-export"
    export_manifest = FlightExporter().export(
        result.dataset,
        export_directory,
        options=ExportOptions(
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    manifest_path = export_manifest.ManifestPath_Get()
    assert manifest_path is not None
    audit = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert audit["source_log"]["sha256"] == hashlib.sha256(log_path.read_bytes()).hexdigest()
    assert audit["decoder_profile"]["package_sha256"] == result.package.package_sha256
    assert audit["decoder_profile"]["match_mode"] == "exact_generation_profile"
    assert audit["firmware"]["algorithm_components"] == ["silverstar.algorithm.estimator.kf6"]
    assert audit["calibration"]["identity_model"] is True
    assert "imu.native.accel_b" not in audit["stable_aliases"]


def test_none_identity_is_legal_with_six_face_config_and_nonzero_start_sequence(
    tmp_path: Path,
) -> None:
    semantics = _SemanticsDocument_Build()
    semantics["modes"] = {"calibration": ["SixFace"]}
    files, _ = _PackageFiles_Build(semantics_document=semantics)
    package_path, hashes = _Package_Write(
        tmp_path / "none_with_six_face.ssdecoder",
        files=files,
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 5,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(start_sequence=1),
        START_TIMESTAMP_US - 4,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(samples=1, start_sequence=2),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    result = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    ).Open(
        LogOpenRequest(
            log_path=builder.File_Write(tmp_path / "none_with_six_face.sslog"),
            decoder_package_path=package_path,
        )
    )

    calibration = result.dataset.semantic_context.calibration
    assert len(result.dataset.Records_Get("CALIBRATION_RESULT")) == 2
    assert calibration.mode_name == "NONE"
    assert calibration.identity_model
    assert calibration.start_sequence == 1
    assert calibration.timestamp_us == START_TIMESTAMP_US - 4
    assert result.parse_diagnostics is result.dataset.diagnostics
    assert result.data_quality is result.dataset.data_quality


def test_file_order_timestamps_may_regress_while_each_channel_is_sorted(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "time_order.ssdecoder")
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 20, (2.0, 0.0, 0.0)),
        START_TIMESTAMP_US + 20,
    )
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 10, (1.0, 0.0, 0.0)),
        START_TIMESTAMP_US + 10,
    )
    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(builder.File_Write(tmp_path / "time_order.sslog"))

    records = dataset.Records_Get("IMU_NATIVE")
    assert [record.timestamp_us for record in records] == [
        START_TIMESTAMP_US + 20,
        START_TIMESTAMP_US + 10,
    ]
    series = dataset.Series_Get("IMU_NATIVE:1:0.accel_b_mps2")
    assert series is not None
    assert series.timestamp_us.tolist() == [
        START_TIMESTAMP_US + 10,
        START_TIMESTAMP_US + 20,
    ]
    assert series.values[:, 0].tolist() == [1.0, 2.0]


def test_current_container_resync_rejects_false_magic_until_crc_valid_candidate(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "resync.ssdecoder")
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    false_header = struct.pack(
        "<IBBHIQI",
        0x31474C46,
        0,
        0x02,
        4,
        99,
        START_TIMESTAMP_US,
        0,
    )
    false_payload = b"FAKE"
    false_crc = (zlib.crc32(false_header + false_payload) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    builder.records[0] += (
        b"DAMAGED"
        + false_header
        + false_payload
        + struct.pack("<I", false_crc)
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(builder.File_Write(tmp_path / "resync.sslog"))

    assert dataset.diagnostics.record_count == 2
    assert dataset.diagnostics.resync_count == 1
    assert dataset.diagnostics.resync_candidate_count == 2
    assert dataset.diagnostics.record_crc_failures == 0
    assert len(dataset.diagnostics.damaged_spans) == 1
    assert dataset.diagnostics.damaged_spans[0].reason == "sync_loss"
    assert dataset.diagnostics.damaged_spans[0].raw_hex.startswith(
        b"DAMAGED".hex().upper()
    )
    assert dataset.metadata["parse_status"] == "partial"


def test_current_container_recovers_from_invalid_length_at_expected_boundary(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "length.ssdecoder")
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.records[0] += struct.pack(
        "<IBBHIQI",
        0x31474C46,
        0,
        0x02,
        500,
        99,
        START_TIMESTAMP_US,
        0,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(builder.File_Write(tmp_path / "length.sslog"))

    assert dataset.diagnostics.record_length_failures == 1
    assert dataset.diagnostics.resync_count == 1
    assert dataset.diagnostics.recovered_after_sync_loss == 1
    assert len(dataset.Records_Get("EVENT")) == 1


def test_current_container_resync_scan_is_bounded(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x02, Event_Payload(0x01), START_TIMESTAMP_US)
    builder.records[0] += b"X" * 64
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 1)
    path = builder.File_Write(tmp_path / "bounded_resync.sslog")
    container = Sslog0ContainerPlugin()
    diagnostics = ParserDiagnostics()
    with path.open("rb") as source:
        options = ParseOptions(
            diagnostics=diagnostics,
            source_size=path.stat().st_size,
            maximum_resync_scan_bytes=16,
            maximum_resync_candidates=2,
        )
        container.header_read(source, options)
        frames = tuple(container.iter_frames(source, options))

    assert len(frames) == 1
    assert diagnostics.resync_failure_count == 1
    assert diagnostics.truncated_tail


def test_default_channel_template_does_not_alias_descriptor_namespaces() -> None:
    catalog_document = _CatalogDocument_Build()
    catalog_document["records"].append(
        {
            "id": "0x41",
            "version": 0,
            "name": "DEVICE_DESCRIPTOR",
            "payload_size": 7,
            "fields": [
                {"name": "descriptor_id", "type": "u16"},
                {"name": "instance_id", "type": "u8"},
                {"name": "physical_device_id", "type": "u16"},
                {"name": "status", "type": "u16"},
            ],
        }
    )
    semantics_document = _SemanticsDocument_Build()
    semantics_document["record_views"].append(
        {
            "record": "FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR",
            "record_type": "0x41",
            "record_version": 0,
            "payload_size": 7,
            "partition_by": ["instance_id", "physical_device_id"],
            "columns": ["status"],
        }
    )
    semantics = ProjectSemantics.FromDocument(
        semantics_document
    ).Catalog_Bind(RecordCatalog.FromDocument(catalog_document))

    definitions = semantics.ChannelDefinitions_Get(
        "DEVICE_DESCRIPTOR",
        {
            "descriptor_id": 1,
            "instance_id": 0,
            "physical_device_id": 10,
            "status": 7,
        },
    )
    assert definitions[0].channel_id == "DEVICE_DESCRIPTOR:0:10.status"


def test_gnss_online_without_fix_and_zero_measurements_is_legal(
    tmp_path: Path,
) -> None:
    catalog_document = _CatalogDocument_Build()
    catalog_document["records"].append(
        {
            "id": "0x42",
            "version": 0,
            "name": "GNSS_NATIVE",
            "payload_size": 24,
            "fields": [
                {"name": "source_descriptor_id", "type": "u16"},
                {"name": "instance_id", "type": "u8"},
                {"type": "pad", "count": 1},
                {"name": "sample_timestamp_us", "type": "u64"},
                {"name": "online", "type": "u8"},
                {"name": "fix_type", "type": "u8"},
                {"name": "position_usable", "type": "u8"},
                {"name": "velocity_valid_mask", "type": "u8"},
                {"name": "latitude_e7", "type": "u32"},
                {"name": "longitude_e7", "type": "u32"},
            ],
        }
    )
    semantics_document = _SemanticsDocument_Build()
    semantics_document["record_views"].append(
        {
            "record": "FLIGHT_LOG_RECORD_GNSS_NATIVE",
            "record_type": "0x42",
            "record_version": 0,
            "payload_size": 24,
            "partition_by": ["source_descriptor_id", "instance_id"],
            "columns": [
                "online",
                "fix_type",
                "position_usable",
                "velocity_valid_mask",
                "latitude_e7",
                "longitude_e7",
            ],
        }
    )
    semantics_document["logging_streams"].extend(
        [
            {
                "record": "FLIGHT_LOG_RECORD_GNSS_NATIVE",
                "enabled": True,
            },
            {
                "record": "FLIGHT_LOG_RECORD_GNSS_MEASUREMENT",
                "enabled": True,
            },
        ]
    )
    files, _ = _PackageFiles_Build(
        catalog_document=catalog_document,
        semantics_document=semantics_document,
    )
    package_path, hashes = _Package_Write(
        tmp_path / "gnss_no_fix.ssdecoder",
        files=files,
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 3,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(start_sequence=1),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    builder.Record_Add(
        0x42,
        struct.pack(
            "<HBxQ4BII",
            2,
            1,
            START_TIMESTAMP_US + 1,
            1,
            0,
            0,
            0,
            0,
            0,
        ),
        START_TIMESTAMP_US + 1,
    )
    dataset = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    ).Open(
        LogOpenRequest(
            log_path=builder.File_Write(tmp_path / "gnss_no_fix.sslog"),
            decoder_package_path=package_path,
        )
    ).dataset

    gnss = FlightSummary_Build(dataset).gnss
    assert gnss.native_configured
    assert gnss.measurement_configured
    assert gnss.native_sample_count == 1
    assert gnss.measurement_sample_count == 0
    assert gnss.latest_online
    assert gnss.latest_fix_type == 0
    assert gnss.position_usable_count == 0
    assert gnss.velocity_usable_count == 0


def test_log_open_coordinator_rejects_non_identity_none_calibration(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "bad_none.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 3,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(samples=1),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    log_path = builder.File_Write(tmp_path / "bad_none.sslog")
    coordinator = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    )

    with pytest.raises(
        DecoderProfileError,
        match="calibration_none_identity_invalid",
    ):
        coordinator.Open(
            LogOpenRequest(
                log_path=log_path,
                decoder_package_path=package_path,
            )
        )


def test_project_open_rediscover_exact_package_when_cache_and_source_are_missing(
    tmp_path: Path,
) -> None:
    source_path, hashes = _Package_Write(tmp_path / "source.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 3,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    log_path = builder.File_Write(tmp_path / "flight.sslog")
    imported = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "original-cache"),
    ).Open(
        LogOpenRequest(
            log_path=log_path,
            decoder_package_path=source_path,
        )
    )
    search_root = tmp_path / "relocated-task"
    search_root.mkdir()
    relocated_package = search_root / "renamed.ssdecoder"
    relocated_package.write_bytes(source_path.read_bytes())

    reopened = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "empty-cache"),
    ).Open(
        LogOpenRequest(
            log_path=log_path,
            decoder_package_path=tmp_path / "missing.ssdecoder",
            cache_reference=imported.cache_reference,
            task_directory=search_root,
            source_mode=LogOpenSourceMode.PROJECT,
        )
    )

    assert reopened.package.package_sha256 == imported.package.package_sha256
    assert reopened.source_package_path == relocated_package.resolve()
    assert reopened.dataset.semantic_context is not None


def test_calibration_selects_latest_ready_snapshot_not_after_start(
    tmp_path: Path,
) -> None:
    semantics = _SemanticsDocument_Build()
    semantics["modes"]["calibration"] = ["OneFace", "SixFace"]
    files, hashes = _PackageFiles_Build(semantics_document=semantics)
    package_path, _ = _Package_Write(
        tmp_path / "calibration_modes.ssdecoder",
        files=files,
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1_000,
    )
    builder.Record_Add(
        0x17,
        _CalibrationPayload_Build(
            mode=1,
            completed_face_mask=0x01,
            samples=20,
        ),
        START_TIMESTAMP_US - 500,
    )
    builder.Record_Add(
        0x17,
        _CalibrationPayload_Build(
            mode=2,
            completed_face_mask=0x3F,
            samples=120,
        ),
        START_TIMESTAMP_US - 100,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    builder.Record_Add(
        0x17,
        _CalibrationPayload_Build(
            mode=1,
            completed_face_mask=0x01,
            samples=30,
        ),
        START_TIMESTAMP_US + 100,
    )
    result = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    ).Open(
        LogOpenRequest(
            log_path=builder.File_Write(tmp_path / "calibration_modes.sslog"),
            decoder_package_path=package_path,
        )
    )

    context = result.dataset.semantic_context
    assert context is not None
    assert context.modes["calibration"] == ("OneFace", "SixFace")
    assert context.calibration.mode_name == "SIX_FACE"
    assert context.calibration.timestamp_us == START_TIMESTAMP_US - 100
    assert context.calibration.completed_face_mask == 0x3F
    assert context.calibration.samples == 120


@pytest.mark.parametrize("result_after_start", [False, True])
def test_calibration_missing_or_only_after_start_is_rejected(
    tmp_path: Path,
    result_after_start: bool,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "missing_calibration.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    if result_after_start:
        builder.Record_Add(
            0x17,
            _CalibrationNonePayload_Build(),
            START_TIMESTAMP_US + 1,
        )
    coordinator = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(tmp_path / "cache"),
    )

    with pytest.raises(
        DecoderProfileError,
        match="calibration_result_before_boundary_missing",
    ):
        coordinator.Open(
            LogOpenRequest(
                log_path=builder.File_Write(tmp_path / "missing_calibration.sslog"),
                decoder_package_path=package_path,
            )
        )


def test_cli_inspect_uses_exact_package_and_dynamic_algorithm_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "cli.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 3,
    )
    builder.Record_Add(
        0x17,
        _CalibrationNonePayload_Build(),
        START_TIMESTAMP_US - 2,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    log_path = builder.File_Write(tmp_path / "cli.sslog")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    return_code = Cli_Main(
        [
            "inspect",
            str(log_path),
            "--decoder",
            str(package_path),
        ]
    )

    assert return_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decoder"]["match_mode"] == "exact_generation_profile"
    assert payload["semantic_context"]["calibration"]["mode_name"] == "NONE"
    assert _Algorithm_Resolve(
        builtin_registry(),
        "silverstar.algorithm.kf6",
    ).metadata.display_name == "KF_6"


def test_unknown_type_and_version_retain_raw_payload_and_mark_partial(
    tmp_path: Path,
) -> None:
    package_path, hashes = _Package_Write(tmp_path / "unknown.ssdecoder")
    package = DecoderProfilePackage.Load(
        package_path,
        container_plugins=_ContainerMap_Get(),
    )
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE,
        _DescriptorPayload_Build(hashes),
        START_TIMESTAMP_US - 1,
    )
    builder.Record_Add(0x7F, b"unknown-type", START_TIMESTAMP_US)
    builder.Record_Add(
        IMU_RECORD_TYPE,
        b"unknown-version",
        START_TIMESTAMP_US + 1,
        record_version=9,
    )
    dataset = DecoderProfileParserPlugin(
        Sslog0ContainerPlugin(),
        package,
    ).parse(builder.File_Write(tmp_path / "unknown.sslog"))

    assert dataset.metadata["parse_status"] == "partial"
    assert dataset.diagnostics.unknown_record_type_count == 1
    assert dataset.diagnostics.unknown_record_version_count == 1
    assert (
        dataset.Records_Get("UNKNOWN_0x7F_V0")[0].payload["raw_payload"]
        == b"unknown-type"
    )
    assert (
        dataset.Records_Get(f"UNKNOWN_0x{IMU_RECORD_TYPE:02X}_V9")[0]
        .payload["__partial__"]
        is True
    )


def test_record_catalog_supports_full_scalar_whitelist_and_transforms() -> None:
    fields = [
        {"name": "enum_u8", "type": "u8", "enum": {"1": "ONE"}},
        {"name": "signed_i8", "type": "i8"},
        {
            "name": "flags_u16",
            "type": "u16",
            "bitfield": [{"bit": 1, "name": "READY"}],
        },
        {"name": "scaled_i16", "type": "i16", "scale": 0.5, "offset": 1.0},
        {"name": "plain_u32", "type": "u32"},
        {"name": "plain_i32", "type": "i32"},
        {"name": "plain_u64", "type": "u64"},
        {"name": "plain_i64", "type": "i64"},
        {"name": "plain_f32", "type": "f32"},
        {"name": "plain_f64", "type": "f64"},
        {"name": "array_u16", "type": "u16", "count": 2},
        {"type": "pad", "count": 3},
    ]
    payload = struct.pack(
        "<BbHhIiQqfd2H3x",
        1,
        -2,
        2,
        4,
        5,
        -6,
        7,
        -8,
        9.5,
        10.25,
        11,
        12,
    )
    catalog = RecordCatalog.FromDocument(
        {
            "catalog_schema_id": "silverstar.sslog.record-catalog/1.0",
            "endianness": "little",
            "records": [
                {
                    "id": "0x01",
                    "version": 0,
                    "name": "WHITELIST",
                    "payload_size": len(payload),
                    "fields": fields,
                }
            ],
        }
    )

    decoded = catalog.Layout_Get(1, 0).Decode(payload)  # type: ignore[union-attr]

    assert decoded["enum_u8__enum"] == "ONE"
    assert decoded["flags_u16__bits"] == ("READY",)
    assert decoded["scaled_i16"] == pytest.approx(3.0)
    assert decoded["plain_i64"] == -8
    assert decoded["plain_f64"] == pytest.approx(10.25)
    assert decoded["array_u16"] == (11, 12)


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("zip_slip", "decoder_package_member_path_invalid"),
        ("duplicate", "decoder_package_duplicate_member"),
        ("symlink", "decoder_package_symlink_forbidden"),
        ("executable", "decoder_package_executable_forbidden"),
        ("checksum", "decoder_package_checksum_mismatch"),
    ],
)
def test_decoder_package_rejects_unsafe_or_tampered_zip(
    tmp_path: Path,
    mutation: str,
    error_code: str,
) -> None:
    files, _ = _PackageFiles_Build()
    path = tmp_path / f"{mutation}.ssdecoder"
    if mutation == "checksum":
        files["record_catalog.json"] += b" "
        _Package_Write(path, files=files)
    else:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            if mutation == "zip_slip":
                archive.writestr("../outside.txt", b"bad")
            elif mutation == "duplicate":
                with pytest.warns(UserWarning, match="Duplicate name"):
                    archive.writestr("manifest.json", files["manifest.json"])
            elif mutation == "executable":
                archive.writestr("payload.py", b"raise RuntimeError")
            else:
                link = zipfile.ZipInfo("linked.json")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, b"manifest.json")

    with pytest.raises(DecoderProfileError, match=error_code):
        DecoderProfilePackage.Load(path)


def test_decoder_package_rejects_obsolete_1_0_and_unsigned_layouts(
    tmp_path: Path,
) -> None:
    obsolete_files, _ = _PackageFiles_Build()
    obsolete_manifest = json.loads(obsolete_files["manifest.json"])
    obsolete_manifest["package_schema"] = {
        "id": "silverstar.ssdecoder.package-schema/1.0",
        "major": 1,
        "minor": 0,
    }
    obsolete_files["manifest.json"] = _JsonBytes(obsolete_manifest)
    _Checksums_Refresh(obsolete_files)
    obsolete_path, _ = _Package_Write(
        tmp_path / "obsolete.ssdecoder",
        files=obsolete_files,
    )
    with pytest.raises(
        DecoderProfileError,
        match="decoder_package_format_version_unsupported",
    ):
        DecoderProfilePackage.Load(obsolete_path)

    unsigned_files, _ = _PackageFiles_Build()
    unsigned_files.pop("checksums.sha256")
    unsigned_manifest = json.loads(unsigned_files["manifest.json"])
    unsigned_manifest["entries"].remove("checksums.sha256")
    unsigned_files["manifest.json"] = _JsonBytes(unsigned_manifest)
    unsigned_path = tmp_path / "unsigned.ssdecoder"
    with zipfile.ZipFile(
        unsigned_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, content in unsigned_files.items():
            archive.writestr(name, content)
    with pytest.raises(
        DecoderProfileError,
        match="decoder_package_required_file_missing",
    ):
        DecoderProfilePackage.Load(unsigned_path)


def test_decoder_package_rejects_legacy_manifest_field_aliases(
    tmp_path: Path,
) -> None:
    cases = (
        (
            "format_version",
            lambda manifest: (
                manifest.pop("package_schema"),
                manifest.__setitem__("format_version", 1),
            ),
            "decoder_package_schema_invalid",
        ),
        (
            "container_top_level",
            lambda manifest: (
                manifest.pop("container_plugin"),
                manifest.__setitem__(
                    "container_plugin_id",
                    "silverstar.sslog.container/0.0",
                ),
            ),
            "decoder_container_plugin_requirement_invalid",
        ),
        (
            "catalog_hash_alias",
            lambda manifest: manifest.__setitem__(
                "record_catalog_hash",
                manifest.pop("record_catalog_sha256"),
            ),
            "decoder_record_catalog_hash_missing",
        ),
        (
            "missing_executable_declaration",
            lambda manifest: manifest.pop("contains_executable_code"),
            "decoder_package_executable_declaration_invalid",
        ),
    )
    for name, mutate, expected_error in cases:
        files, _ = _PackageFiles_Build()
        manifest = json.loads(files["manifest.json"])
        mutate(manifest)
        files["manifest.json"] = _JsonBytes(manifest)
        _Checksums_Refresh(files)
        path, _ = _Package_Write(tmp_path / f"{name}.ssdecoder", files=files)
        with pytest.raises(DecoderProfileError, match=expected_error):
            DecoderProfilePackage.Load(path)


def test_decoder_package_rejects_legacy_catalog_and_semantics_shapes(
    tmp_path: Path,
) -> None:
    legacy_catalog = _CatalogDocument_Build()
    catalog_files, _ = _PackageFiles_Build(
        catalog_document={
            "parser_metadata": legacy_catalog,
            "record_schema": legacy_catalog,
        }
    )
    catalog_path, _ = _Package_Write(
        tmp_path / "legacy_catalog.ssdecoder",
        files=catalog_files,
    )
    with pytest.raises(
        DecoderProfileError,
        match="decoder_record_catalog_schema_id_unsupported",
    ):
        DecoderProfilePackage.Load(catalog_path)

    old_semantics = _SemanticsDocument_Build()
    old_semantics["schema_id"] = "silverstar.project-semantics/1.0"
    semantics_files, _ = _PackageFiles_Build(semantics_document=old_semantics)
    semantics_path, _ = _Package_Write(
        tmp_path / "legacy_semantics.ssdecoder",
        files=semantics_files,
    )
    with pytest.raises(
        DecoderProfileError,
        match="decoder_project_semantics_schema_id_unsupported",
    ):
        DecoderProfilePackage.Load(semantics_path)

    mapping_algorithms = _SemanticsDocument_Build()
    mapping_algorithms["algorithms"] = [
        {"component_id": "silverstar.algorithm.estimator.kf6"}
    ]
    algorithm_files, _ = _PackageFiles_Build(
        semantics_document=mapping_algorithms
    )
    algorithm_path, _ = _Package_Write(
        tmp_path / "mapping_algorithms.ssdecoder",
        files=algorithm_files,
    )
    with pytest.raises(
        DecoderProfileError,
        match="decoder_algorithm_catalog_invalid",
    ):
        DecoderProfilePackage.Load(algorithm_path)


def test_catalog_payload_size_mismatch_and_missing_plugin_are_rejected(
    tmp_path: Path,
) -> None:
    files, _ = _PackageFiles_Build(
        catalog_document=_CatalogDocument_Build(payload_size=29)
    )
    mismatch_path, _ = _Package_Write(tmp_path / "bad_size.ssdecoder", files=files)
    with pytest.raises(
        DecoderProfileError,
        match="decoder_record_payload_size_mismatch",
    ):
        DecoderProfilePackage.Load(mismatch_path)

    valid_path, _ = _Package_Write(tmp_path / "missing_plugin.ssdecoder")
    with pytest.raises(DecoderProfileError, match="decoder_container_plugin_missing"):
        DecoderProfilePackage.Load(valid_path, container_plugins={})


def test_package_rejects_future_flp_requirement_and_envelope_conflict(
    tmp_path: Path,
) -> None:
    files, _ = _PackageFiles_Build()
    manifest = json.loads(files["manifest.json"])
    manifest["required_flp_minimum_version"] = "99.0.0"
    files["manifest.json"] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    future_path, _ = _Package_Write(tmp_path / "future.ssdecoder", files=files)
    with pytest.raises(
        DecoderProfileError,
        match="decoder_required_flp_version_not_met",
    ):
        DecoderProfilePackage.Load(future_path)

    legacy = _CatalogDocument_Build()
    with pytest.raises(
        DecoderProfileError,
        match="decoder_record_catalog_schema_id_unsupported",
    ):
        RecordCatalog.FromDocument(
            {
                "parser_metadata": legacy,
                "record_schema": legacy,
            }
        )


def test_manual_import_cache_is_content_addressed_and_reusable(tmp_path: Path) -> None:
    source_path, _ = _Package_Write(tmp_path / "source.ssdecoder")
    source_bytes = source_path.read_bytes()
    cache = DecoderProfileCache(tmp_path / "cache")
    containers = _ContainerMap_Get()

    cached, reference = cache.Package_Import(
        source_path,
        container_plugins=containers,
    )
    loaded = cache.Package_Load(reference, container_plugins=containers)

    assert source_path.read_bytes() == source_bytes
    assert cached.package_sha256 == loaded.package_sha256 == reference.package_sha256
    assert reference.generation_profile_sha256[:32] in reference.relative_path
    assert loaded.source_path != source_path


def test_directory_scan_finds_log_below_and_package_in_bounded_parent(
    tmp_path: Path,
) -> None:
    project = tmp_path / "Mission"
    golden = project / "Logs" / "Golden"
    golden.mkdir(parents=True)
    package_path, _ = _Package_Write(project / "Mission.ssdecoder")
    builder = SyntheticSslogBuilder()
    log_path = builder.File_Write(golden / "mission.sslog")

    result = TaskDirectoryScanner().Scan(golden)

    assert log_path.resolve() in result.log_paths
    assert package_path.resolve() in result.decoder_package_paths
    assert not result.limit_reached


def test_descriptor_hash_normalizes_byte_and_word_arrays() -> None:
    payload = {
        "package_schema_major": 1,
        "package_schema_minor": 1,
        "container_format_major": 1,
        "container_format_minor": 2,
        "record_catalog_hash_128": tuple(range(16)),
        "project_semantics_hash_128": tuple(range(16)),
        "generation_profile_hash_128": bytes(range(16)),
    }

    descriptor = DecoderProfileDescriptor.FromPayload(payload)

    assert descriptor.container_version == "1.2.0"
    assert descriptor.record_catalog_hash_128 == bytes(range(16)).hex()
    assert descriptor.project_semantics_hash_128 == bytes(range(16)).hex()
    assert descriptor.generation_profile_hash_128 == bytes(range(16)).hex()


def test_container_yields_record_agnostic_raw_frame(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        0xEE,
        b"opaque-payload",
        START_TIMESTAMP_US,
        valid_flags=0xA5,
        record_version=7,
        sequence=42,
    )
    path = builder.File_Write(tmp_path / "opaque.sslog")
    container = Sslog0ContainerPlugin()
    diagnostics = ParserDiagnostics()
    with path.open("rb") as source:
        options = ParseOptions(diagnostics=diagnostics, source_size=path.stat().st_size)
        header = container.header_read(source, options)
        frames = tuple(container.iter_frames(source, options))

    assert header["magic"] == "SSLOG0"
    assert len(frames) == 1
    assert frames[0].record_type == 0xEE
    assert frames[0].record_version == 7
    assert frames[0].sequence == 42
    assert frames[0].valid_flags == 0xA5
    assert frames[0].payload_bytes == b"opaque-payload"
    assert frames[0].crc_valid


def test_source_descriptor_partition_keeps_capabilities_linked_not_merged() -> None:
    document = _SemanticsDocument_Build()
    document["device_descriptors"][1]["physical_device_id"] = 10
    document["capability_endpoints"][1]["physical_device_id"] = 10
    document["capability_endpoints"][1]["device_class"] = "barometer"
    semantics = ProjectSemantics.FromDocument(document).Catalog_Bind(
        RecordCatalog.FromDocument(_CatalogDocument_Build())
    )

    first = semantics.ChannelDefinitions_Get(
        "IMU_NATIVE",
        {
            "source_descriptor_id": 1,
            "instance_id": 0,
            "accel_b_mps2": (1.0, 2.0, 3.0),
        },
    )[0]
    second = semantics.ChannelDefinitions_Get(
        "IMU_NATIVE",
        {
            "source_descriptor_id": 2,
            "instance_id": 1,
            "accel_b_mps2": (4.0, 5.0, 6.0),
        },
    )[0]

    assert first.channel_id != second.channel_id
    assert first.metadata["physical_device_id"] == second.metadata["physical_device_id"] == 10
    assert first.metadata["capability_class"] == "imu"
    assert second.metadata["capability_class"] == "barometer"


class _TrustedTestContainer(LogContainerPlugin):
    metadata = LogContainerMetadata(
        plugin_id="example.container.test",
        container_format_id="TEST",
        version="1.2.3",
        api_version=1,
        display_name="Test",
    )

    def probe(self, source: Any) -> ProbeResult:
        return ProbeResult(0.0, "TEST")

    def header_read(self, source: Any, options: Any) -> dict[str, Any]:
        return {}

    def iter_frames(self, source: Any, options: Any) -> Any:
        return iter(())


def _Ssplugin_Write(path: Path, plugin_id: str = "example.container.test") -> Path:
    manifest = {
        "format": "SilverStar.ssplugin",
        "plugin_type": "log_container",
        "plugin_id": plugin_id,
        "version": "1.2.3",
        "api_version": 1,
        "entry_point": "trusted.test:factory",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", _JsonBytes(manifest))
        archive.writestr("plugin.py", b"# inert until a trusted host factory is supplied\n")
    return path


def test_ssplugin_requires_explicit_trust_and_host_factory_allowlist(
    tmp_path: Path,
) -> None:
    source = _Ssplugin_Write(tmp_path / "test.ssplugin")
    manager = TrustedContainerPluginManager(tmp_path / "installed")
    with pytest.raises(
        DecoderProfileError,
        match="container_plugin_explicit_trust_required",
    ):
        manager.Package_Install(source, explicitly_trusted=False)

    manifest = manager.Package_Install(source, explicitly_trusted=True)
    discovery = manager.Discover()

    assert discovery.manifests == (manifest,)
    with pytest.raises(
        DecoderProfileError,
        match="container_plugin_factory_not_trusted",
    ):
        manager.Container_Load(manifest, {})
    plugin = manager.Container_Load(
        manifest,
        {"trusted.test:factory": _TrustedTestContainer},
    )
    assert plugin.metadata.plugin_id == "example.container.test"


def test_ssplugin_cannot_replace_builtin_container(tmp_path: Path) -> None:
    source = _Ssplugin_Write(
        tmp_path / "override.ssplugin",
        plugin_id="silverstar.flight_log.container.0_0",
    )
    manager = TrustedContainerPluginManager(tmp_path / "installed")

    with pytest.raises(
        DecoderProfileError,
        match="container_plugin_builtin_protected",
    ):
        manager.Package_Install(source, explicitly_trusted=True)
