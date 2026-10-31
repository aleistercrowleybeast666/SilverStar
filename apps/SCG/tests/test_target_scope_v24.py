"""Normal project ownership and exact target selection regressions."""
from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.generation_state import TargetGenerationInputHash_Get
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent, TargetGenerationReceipt_Get
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.telemetry import TelemetryProfile_Apply
from silverstar_fccg.project.validation import Project_Validate


def _Project_Create(catalog):
    return TelemetryProfile_Apply(ReferenceProject_Create('Scope24', catalog=catalog),
                                 catalog, 'ss_tm.s.0_1')


@pytest.mark.parametrize('old_enabled', (False, True))
def test_versioned_ground_migration_preserves_configuration(builtin_catalog, old_enabled):
    original = _Project_Create(builtin_catalog).Dictionary_Get()
    original['format_version'] = 23
    original['ground_target']['enabled'] = old_enabled
    original['ground_target']['pc_interface'] = 'uart'
    original['ground_target']['pc_resource'] = 'PLATFORM_UART_1'
    before = deepcopy(original)
    migrated = ProjectModel_Parse(original)
    assert original == before
    assert migrated.Dictionary_Get()['format_version'] == 24
    ground = migrated.Dictionary_Get()['ground_target']
    assert 'enabled' not in ground
    assert ground == {key: value for key, value in before['ground_target'].items() if key != 'enabled'}


def test_new_schema_rejects_reintroduced_enable_gate(builtin_catalog):
    value = _Project_Create(builtin_catalog).Dictionary_Get()
    value['ground_target']['enabled'] = True
    with pytest.raises(ProjectModelError, match='ground_target'):
        ProjectModel_Parse(value)


def test_target_private_changes_invalidate_only_own_generation(builtin_catalog):
    model = _Project_Create(builtin_catalog)
    hashes = {target: TargetGenerationInputHash_Get(model, target) for target in ('flight', 'ground')}
    model.ground_target = replace(model.ground_target, baudrate=115200)
    assert TargetGenerationInputHash_Get(model, 'flight') == hashes['flight']
    assert TargetGenerationInputHash_Get(model, 'ground') != hashes['ground']
    ground_hash = TargetGenerationInputHash_Get(model, 'ground')
    model.build = replace(model.build, memory_layout='auto')
    assert TargetGenerationInputHash_Get(model, 'flight') != hashes['flight']
    assert TargetGenerationInputHash_Get(model, 'ground') == ground_hash
    flight_hash = TargetGenerationInputHash_Get(model, 'flight')
    model.air_link = replace(model.air_link, frequency_hz=model.air_link.frequency_hz + 1000000)
    assert TargetGenerationInputHash_Get(model, 'flight') != flight_hash
    assert TargetGenerationInputHash_Get(model, 'ground') != ground_hash


def test_flight_validation_does_not_require_ground_board(builtin_catalog):
    model = _Project_Create(builtin_catalog)
    assert not model.ground_target.mcu
    assert not [issue for issue in Project_Validate(model, builtin_catalog).issues
                if issue.level == 'error'], Project_Validate(model, builtin_catalog).issues


def test_host_paths_and_ui_descriptions_do_not_change_target_digest(builtin_catalog):
    model = _Project_Create(builtin_catalog)
    before = TargetGenerationInputHash_Get(model, 'flight')
    model.hardware = replace(model.hardware, source_label='translated label', risk_acknowledged=True)
    model.build = replace(model.build, gcc_path='D:/another/compiler', make_command='another-make')
    assert TargetGenerationInputHash_Get(model, 'flight') == before


def test_target_receipt_requires_matching_configuration_and_component_locks(builtin_catalog, tmp_path):
    import json
    from test_round2_targets import _GroundBoardProject_Get
    model = _GroundBoardProject_Get(builtin_catalog)
    generated = tmp_path / 'Generated'; generated.mkdir()
    def Write(target, name):
        value = TargetGenerationReceipt_Get(model, builtin_catalog, target)
        (generated / name).write_text(json.dumps(value), encoding='utf-8')
    assert not ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'flight')
    Write('flight', 'memory_contract.json'); Write('ground', 'ground_target_metadata.json')
    assert ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'flight')
    assert ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'ground')
    model.ground_target = replace(model.ground_target, baudrate=57600)
    assert ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'flight')
    assert not ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'ground')
    model.air_link = replace(model.air_link, frequency_hz=model.air_link.frequency_hz + 1000000)
    assert not ProjectTargetGenerated_IsCurrent(model, builtin_catalog, tmp_path, 'flight')


def test_payload_bytes_and_complete_owner_set_are_part_of_receipt(builtin_catalog, tmp_path):
    """Use an isolated owner payload; no built-in source is mutated by this test."""
    import json
    from types import SimpleNamespace
    model = _Project_Create(builtin_catalog)
    original = builtin_catalog.Component_Get(model.core)
    payload = tmp_path / 'payload'; payload.mkdir()
    source = payload / 'owner.c'; source.write_text('int version = 1;\n', encoding='utf-8')
    templates = tmp_path / 'templates'; templates.mkdir()
    template = templates / 'config.h'; template.write_text('#define CONFIG 1\n', encoding='utf8')
    isolated = SimpleNamespace(version=original.version, source=original.source,
        component_id=original.component_id, payload_root=payload, package_root=tmp_path,
        PayloadFiles_Get=lambda: [source], ManifestSha256_Get=original.ManifestSha256_Get)
    catalog = SimpleNamespace(Component_Get=lambda identity:
        isolated if identity == model.core else builtin_catalog.Component_Get(identity))
    generated = tmp_path / 'Generated'; generated.mkdir()
    path = generated / 'memory_contract.json'
    receipt = TargetGenerationReceipt_Get(model, catalog, 'flight')
    path.write_text(json.dumps(receipt), encoding='utf-8')
    assert ProjectTargetGenerated_IsCurrent(model, catalog, tmp_path, 'flight')
    source.write_text('int version = 2;\n', encoding='utf-8')
    assert not ProjectTargetGenerated_IsCurrent(model, catalog, tmp_path, 'flight')
    current = TargetGenerationReceipt_Get(model, catalog, 'flight')
    assert current['generation_input_sha256'] == receipt['generation_input_sha256']
    assert current['component_locks'][model.core]['manifest_sha256'] == receipt['component_locks'][model.core]['manifest_sha256']
    assert current['component_locks'][model.core]['payload_sha256'] != receipt['component_locks'][model.core]['payload_sha256']
    path.write_text(json.dumps(current), encoding='utf-8')
    assert ProjectTargetGenerated_IsCurrent(model, catalog, tmp_path, 'flight')
    template.write_text('#define CONFIG 2\n', encoding='utf8')
    assert not ProjectTargetGenerated_IsCurrent(model, catalog, tmp_path, 'flight')
    current = TargetGenerationReceipt_Get(model, catalog, 'flight')
    current['component_locks'].pop(next(iter(current['component_locks'])))
    path.write_text(json.dumps(current), encoding='utf-8')
    assert not ProjectTargetGenerated_IsCurrent(model, catalog, tmp_path, 'flight')
