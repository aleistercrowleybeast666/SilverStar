"""Exact-package magnetic source routing; synthetic evidence, no mounting claims."""
from pathlib import Path
import hashlib
import json
import struct

import pytest

from silverstar_flp.decoder_profiles import DecoderProfileCache, DecoderProfileError
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import START_TIMESTAMP_US, Event_Payload, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    _CalibrationNonePayload_Build,
    _CatalogDocument_Build,
    _DescriptorPayload_Build,
    _PackageFiles_Build,
    _Package_Write,
    _SemanticsDocument_Build,
)


def _MagPackage_Create(tmp_path, descriptors, *, route=None, declare=True):
    catalog = _CatalogDocument_Build()
    catalog["records"].append({
        "id": "0x11", "version": 0, "name": "MAG_NATIVE", "payload_size": 60,
        "fields": [{"name": "source_descriptor_id", "type": "u16"},
                   {"name": "instance_id", "type": "u8"}, {"type": "pad"},
                   {"name": "sample_timestamp_us", "type": "u64"},
                   {"name": "receive_timestamp_us", "type": "u64"},
                   {"name": "sequence", "type": "u32"},
                   {"name": "raw", "type": "i32", "count": 3},
                   {"name": "magnetic_field_b_uT", "type": "f32", "count": 3},
                   {"name": "temperature_c", "type": "f32"},
                   {"name": "valid_mask", "type": "u32"},
                   {"name": "calibration_valid", "type": "u8"},
                   {"type": "pad", "count": 3}],
    })
    semantics = _SemanticsDocument_Build()
    if declare:
        for instance, descriptor in enumerate(descriptors):
            device = {"descriptor_id": descriptor, "physical_device_id": 50 + instance,
                      "device_class": "SYSTEM_DEVICE_CLASS_MAGNETOMETER",
                      "instance_id": instance, "source_component": "fixture.mag",
                      "source_instance_id": f"mag{instance}"}
            semantics["device_descriptors"].append(device)
            semantics["capability_endpoints"].append({
                **device, "plugin": "fixture.mag", "model": "Synthetic unqualified MAG",
                "capabilities": ["magnetometer.field"],
            })
    semantics["record_views"].append({
        "record": "FLIGHT_LOG_RECORD_MAG_NATIVE", "record_type": "0x11",
        "record_version": 0, "payload_size": 60,
        "partition_by": ["source_descriptor_id", "instance_id"],
        "columns": ["magnetic_field_b_uT", "raw", "calibration_valid"],
    })
    if route is not None:
        semantics["canonical_channels"].append({
            "channel_id": "canonical:magnetometer.field", "capability": "magnetometer.field",
            "endpoint_descriptor_ids": route,
        })
    files, hashes = _PackageFiles_Build(catalog_document=catalog, semantics_document=semantics)
    return _Package_Write(tmp_path / "mag.ssdecoder", files=files)[0], hashes


def _Open(tmp_path, descriptors, *, route=None, declare=True, recorded=None):
    package, hashes = _MagPackage_Create(tmp_path, descriptors, route=route, declare=declare)
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(3), START_TIMESTAMP_US)
    for instance, descriptor in enumerate(descriptors):
        if recorded is not None and descriptor not in recorded:
            continue
        payload = struct.pack("<HBxQQI3i3ffIB3x", descriptor, instance,
                              START_TIMESTAMP_US + instance + 1,
                              START_TIMESTAMP_US + instance + 2, instance + 1,
                              100, -200, 300, 10.0 + instance, -20.0, 30.0, 25.0, 3, 0)
        builder.Record_Add(0x11, payload, START_TIMESTAMP_US + instance + 2)
    log = builder.File_Write(tmp_path / "mag.sslog")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (package, log)}
    dataset = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(log_path=log, decoder_package_path=package)).dataset
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    return dataset


@pytest.mark.parametrize("descriptor", [5, 29, 13])
def test_single_declared_source_routes_without_fixed_descriptor(tmp_path: Path, descriptor):
    dataset = _Open(tmp_path, [descriptor])
    raw = f"MAG_NATIVE:{descriptor}:0.magnetic_field_b_uT"
    assert dataset.series["mag.native.field_b"] is dataset.series[raw]
    assert dataset.series[raw].values.tolist() == [[10.0, -20.0, 30.0]]
    assert dataset.series[raw].metadata["physical_device_id"] == 50
    assert dataset.series[f"MAG_NATIVE:{descriptor}:0.calibration_valid"].values.tolist() == [0]


@pytest.mark.parametrize("recorded", [None, [13]])
def test_multiple_sources_without_route_keep_only_instance_channels(tmp_path: Path, recorded):
    dataset = _Open(tmp_path, [13, 29], recorded=recorded)
    assert "mag.native.field_b" not in dataset.series
    for instance, descriptor in enumerate([13, 29]):
        raw = f"MAG_NATIVE:{descriptor}:{instance}.magnetic_field_b_uT"
        if recorded is None or descriptor in recorded:
            assert dataset.series[raw].metadata["instance_id"] == instance
            assert dataset.series[raw].metadata["physical_device_id"] == 50 + instance


def test_exact_package_can_select_one_of_multiple_sources(tmp_path: Path):
    dataset = _Open(tmp_path, [13, 29], route=[29])
    raw = "MAG_NATIVE:29:1.magnetic_field_b_uT"
    assert dataset.series["mag.native.field_b"] is dataset.series[raw]
    assert dataset.series["canonical:magnetometer.field"] is dataset.series[raw]


def test_undeclared_legacy_number_never_guesses_source(tmp_path: Path):
    dataset = _Open(tmp_path, [13], declare=False)
    assert "MAG_NATIVE:13:0.magnetic_field_b_uT" in dataset.series
    assert "mag.native.field_b" not in dataset.series


@pytest.mark.parametrize("route", [[99], [13, 29], [1], [True]])
def test_invalid_or_ambiguous_mag_route_rejected(tmp_path: Path, route):
    with pytest.raises(DecoderProfileError, match="canonical_route"):
        _Open(tmp_path, [13, 29], route=route)


def test_retained_legacy_catalog_and_semantics_decode_without_rewriting(tmp_path: Path):
    fixtures = Path(__file__).parent / "fixtures/parameter_contracts"
    sources = [fixtures / f"synthetic_navigation_{name}.json"
               for name in ("catalog", "semantics")]
    before = [path.read_bytes() for path in sources]
    catalog, semantics = [json.loads(content) for content in before]
    files, hashes = _PackageFiles_Build(catalog_document=catalog, semantics_document=semantics)
    package = _Package_Write(tmp_path / "legacy.ssdecoder", files=files)[0]
    package_bytes = package.read_bytes()
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(3), START_TIMESTAMP_US)
    builder.Record_Add(0x11, struct.pack(
        "<HBxQQI3i3ffIB3x", 13, 0, START_TIMESTAMP_US + 1, START_TIMESTAMP_US + 2,
        1, 100, -200, 300, 10., -20., 30., 25., 3, 0), START_TIMESTAMP_US + 2)
    log = builder.File_Write(tmp_path / "legacy.sslog")
    log_bytes = log.read_bytes()
    dataset = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(log_path=log, decoder_package_path=package)).dataset
    assert dataset.series["mag.native.field_b"] is dataset.series["MAG_NATIVE:13:0.magnetic_field_b_uT"]
    assert [path.read_bytes() for path in sources] == before
    assert package.read_bytes() == package_bytes and log.read_bytes() == log_bytes
