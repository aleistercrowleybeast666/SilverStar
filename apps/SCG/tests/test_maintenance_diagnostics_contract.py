"""Maintenance 0.1 is additive; no legacy profile or wire axis is relabelled."""
import json
from dataclasses import replace
from pathlib import Path

from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.protocols import ProtocolResolution_Resolve
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.generator.render import MetadataFiles_Render


def test_legacy_profile_remains_explicit_and_resolvable(builtin_catalog):
    model = ReferenceProject_Create('LegacyMaintenance', catalog=builtin_catalog)
    assert model.protocols['maintenance'].profile == 'maintenance.serial.0_1'
    model.protocols['maintenance'] = replace(model.protocols['maintenance'], profile='maintenance.serial.0_0')
    resolution = ProtocolResolution_Resolve(model, builtin_catalog)
    assert resolution.valid
    binding = next(item for item in resolution.bindings if item.service == 'maintenance_service')
    assert binding.profile_id == 'maintenance.serial.0_0'
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert 'System/Src/system_console.c' in graph.sources
    metadata = MetadataFiles_Render(model, builtin_catalog, graph)
    assert metadata
    assert model.protocols['maintenance'].profile == 'maintenance.serial.0_0'


def test_shared_schema_and_protocol_versions_are_independent():
    root = Path(__file__).resolve().parents[3]
    contract = json.loads((root / 'contracts/maintenance_diagnostics_v1.json').read_text())
    assert contract['schema_version'] == 1
    assert contract['maintenance_version'] == '0.1'
    assert contract['compatible_maintenance_versions'] == ['0.0']
    assert contract['limits']['entries'] == 16
    assert contract['limits']['response_bytes_excluding_crlf'] == 511
    assert contract['independent_versions'] == dict(file_service=1, log_container='SSLOG 0.0', decoder_package='1.2', product='0.1.3')
    package = root / 'apps/SCG/plugins/builtin/silverstar_protocol_maintenance_serial_0_0'
    legacy = json.loads((package / 'payload/Protocol/metadata/maintenance_serial_0_0.json').read_text())
    modern = json.loads((package / 'payload/Protocol/metadata/maintenance_serial_0_1.json').read_text())
    assert legacy != modern
    assert modern['maintenance_version'] == '0.1'
