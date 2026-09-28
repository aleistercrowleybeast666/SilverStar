from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.decoder_profiles import (
    DecoderProfileCache,
    DecoderProfileMatcher,
    DecoderProfilePackage,
    TaskDirectoryScanner,
)
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportOptions,
    FlightExporter,
)
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow

_ROOT_ENVIRONMENT = "SILVERSTAR_SS_TEST_0_ROOT"


def _Paths_Get() -> tuple[Path, Path, Path, Path]:
    root_text = os.environ.get(_ROOT_ENVIRONMENT)
    if not root_text:
        pytest.skip(
            f"set {_ROOT_ENVIRONMENT} for the real FCCG Golden-log validation gate"
        )
    root = Path(root_text)
    package_path = root / "SS_TEST_0.ssdecoder"
    golden_path = root / "Logs" / "Golden" / "SS_TEST_0_golden.sslog"
    expected_path = root / "Logs" / "Golden" / "expected.json"
    missing = [
        path
        for path in (root, package_path, golden_path, expected_path)
        if not path.exists()
    ]
    if missing:
        pytest.skip(f"real FCCG validation input is unavailable: {missing[0]}")
    return root, package_path, golden_path, expected_path


def _Sha256_Get(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _Containers_Get() -> dict[str, Any]:
    registry = builtin_registry()
    return {
        plugin.metadata.plugin_id: plugin
        for plugin in registry.log_containers
    }


def _JsonCompatible_Get(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _JsonCompatible_Get(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_JsonCompatible_Get(item) for item in value]
    return value


def _PackageAndDataset_Get(
    cache_root: Path,
) -> tuple[DecoderProfilePackage, Any, dict[str, Any]]:
    _root, package_path, golden_path, expected_path = _Paths_Get()
    opened = LogOpenCoordinator(
        builtin_registry(),
        cache=DecoderProfileCache(cache_root),
    ).Open(
        LogOpenRequest(
            log_path=golden_path,
            decoder_package_path=package_path,
        )
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    return opened.package, opened.dataset, expected


def _ChannelId_Get(
    package: DecoderProfilePackage,
    dataset: Any,
    record_name: str,
    field_name: str,
) -> str:
    records = dataset.Records_Get(record_name)
    assert len(records) == 1
    definitions = package.semantics.ChannelDefinitions_Get(
        record_name,
        records[0].payload,
    )
    matches = [
        definition.channel_id
        for definition in definitions
        if definition.field_name == field_name
    ]
    assert len(matches) == 1
    return matches[0]


def test_ss_test_0_real_package_discovery_manual_import_and_cache(
    tmp_path: Path,
) -> None:
    root, package_path, golden_path, expected_path = _Paths_Get()
    source_hashes = {
        path: _Sha256_Get(path)
        for path in (package_path, golden_path, expected_path)
    }
    containers = _Containers_Get()
    root_scan = TaskDirectoryScanner().Scan(root)
    golden_scan = TaskDirectoryScanner().Scan(golden_path.parent)
    assert package_path.resolve() in root_scan.decoder_package_paths
    assert golden_path.resolve() in root_scan.log_paths
    assert package_path.resolve() in golden_scan.decoder_package_paths
    assert golden_path.resolve() in golden_scan.log_paths

    matcher = DecoderProfileMatcher(containers)
    match = matcher.Match(golden_path, root_scan.decoder_package_paths)
    assert match.descriptor_found
    assert not match.errors
    assert len(match.matches) == 1
    assert match.matches[0].reason == "exact_generation_profile"

    cache = DecoderProfileCache(tmp_path / "decoder-cache")
    cached, reference = cache.Package_Import(
        package_path,
        container_plugins=containers,
    )
    reloaded = cache.Package_Load(reference, container_plugins=containers)
    assert cached.package_sha256 == source_hashes[package_path]
    assert reloaded.package_sha256 == cached.package_sha256
    assert reloaded.generation_profile_sha256 == cached.generation_profile_sha256
    assert {
        path: _Sha256_Get(path)
        for path in (package_path, golden_path, expected_path)
    } == source_hashes


def test_ss_test_0_real_golden_matches_expected_exactly(tmp_path: Path) -> None:
    package, dataset, expected = _PackageAndDataset_Get(tmp_path / "decoder-cache")
    expected_records: list[dict[str, Any]] = []
    for declared in expected["records"]:
        records = dataset.Records_Get(str(declared["name"]))
        assert len(records) == 1
        record = records[0]
        expected_records.append(
            {
                "id": f"0x{record.record_type:02X}",
                "name": record.record_name,
                "version": record.record_version,
            }
        )
    actual = {
        "schema_id": "silverstar.golden-sslog-expectation/1.0",
        "project": package.semantics.project_name,
        "golden_log": dataset.source_path.name,
        "generator": "Tests/Host/generate_golden_sample.c",
        "codec_sources": [
            "Protocol/SSLOG/Src/sslog_protocol.c",
            "Protocol/SSLOG/Src/sslog_records.c",
        ],
        "record_catalog_sha256": package.catalog.sha256,
        "project_semantics_sha256": package.semantics.sha256,
        "generation_profile_sha256": package.generation_profile_sha256,
        "records": expected_records,
        "canonical_channels": _JsonCompatible_Get(
            package.semantics.canonical_channels
        ),
        "capability_endpoints": _JsonCompatible_Get(
            package.semantics.raw_metadata.get("capability_endpoints", [])
        ),
    }
    assert actual == expected
    assert dataset.metadata["decoder_profile_match_mode"] == "exact_generation_profile"
    assert dataset.metadata["parse_status"] == "complete"
    assert dataset.metadata["container_plugin_id"] == (
        "silverstar.flight_log.container.0_0"
    )
    assert dataset.metadata["decoder_profile_declared_container_plugin_id"] == (
        "silverstar.sslog.container/0.0"
    )
    assert dataset.diagnostics.header_valid
    assert dataset.diagnostics.header_crc_valid
    assert dataset.diagnostics.record_count == len(expected_records)
    assert dataset.diagnostics.decoded_record_count == len(expected_records)
    assert dataset.diagnostics.record_crc_failures == 0
    assert dataset.diagnostics.decoder_failure_count == 0
    assert dataset.diagnostics.unknown_record_type_count == 0
    assert dataset.diagnostics.unknown_record_version_count == 0
    assert not dataset.diagnostics.truncated_tail

    descriptor = dataset.Records_Get("DECODER_PROFILE_DESCRIPTOR")[0]
    assert bytes(descriptor.payload["record_catalog_hash_128"]) == bytes.fromhex(
        package.catalog.sha256
    )[:16]
    assert bytes(descriptor.payload["project_semantics_hash_128"]) == bytes.fromhex(
        package.semantics.sha256
    )[:16]
    assert bytes(descriptor.payload["generation_profile_hash_128"]) == bytes.fromhex(
        package.generation_profile_sha256
    )[:16]

    checks = (
        ("IMU_NATIVE", "accel_b_mps2", 9.80665),
        ("GNSS_NATIVE", "latitude_e7", 320000000.0),
        ("BARO_NATIVE", "pressure_pa", 101325.0),
    )
    endpoints = {
        int(endpoint["descriptor_id"]): endpoint
        for endpoint in expected["capability_endpoints"]
    }
    for record_name, field_name, expected_value in checks:
        channel_id = _ChannelId_Get(package, dataset, record_name, field_name)
        series = dataset.Series_Get(channel_id)
        record = dataset.Records_Get(record_name)[0]
        assert series is not None
        assert float(series.values[0][-1] if series.values.ndim > 1 else series.values[0]) \
            == pytest.approx(expected_value)
        endpoint = endpoints[int(record.payload["source_descriptor_id"])]
        assert series.metadata["descriptor_id"] == endpoint["descriptor_id"]
        assert series.metadata["physical_device_id"] == endpoint["physical_device_id"]
        assert series.metadata["instance_id"] == endpoint["instance_id"]


def test_ss_test_0_real_dataset_existing_gui_and_csv_json_export_smoke(
    tmp_path: Path,
) -> None:
    package, dataset, _expected = _PackageAndDataset_Get(tmp_path / "decoder-cache")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    try:
        window.Language_Apply("zh_CN")
        window.Theme_Apply("light")
        window._Dataset_Set(dataset)
        window.Language_Apply("en_US")
        window.Theme_Apply("dark")
        app.processEvents()
        selected_channels = tuple(
            _ChannelId_Get(package, dataset, record_name, field_name)
            for record_name, field_name in (
                ("IMU_NATIVE", "accel_b_mps2"),
                ("GNSS_NATIVE", "latitude_e7"),
                ("BARO_NATIVE", "pressure_pa"),
            )
        )
        output = tmp_path / "golden-export"
        manifest = FlightExporter().export(
            dataset,
            output,
            options=ExportOptions(
                language=ExportLanguage.EN,
                include_overview=True,
                include_diagnostics=True,
                include_events=True,
                include_csv=True,
                include_full_covariance_keyframes=False,
                include_plots=False,
                include_trajectory_3d=False,
                include_attitude_gif=False,
                selected_channels=selected_channels,
            ),
        )
        assert not manifest.failures
        assert (output / "Flight_Overview_EN.json").is_file()
        assert (output / "Parser_Diagnostics_EN.json").is_file()
        assert (output / "Events_EN.csv").is_file()
        assert len(tuple((output / "CSV_EN").glob("*.csv"))) == len(
            selected_channels
        )
        assert manifest.ManifestPath_Get() is not None
    finally:
        window.close()
