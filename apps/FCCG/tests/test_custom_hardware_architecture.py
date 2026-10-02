"""Custom CubeMX ownership must retain the same architecture rejection paths."""
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.resources import BoardResourceProvisions_Get


@pytest.fixture(scope='module')
def custom_architecture_project(workspace_root, tmp_path_factory):
    service = FccgService(workspace_root)
    root = tmp_path_factory.mktemp('custom_architecture')
    reference = root/'reference'
    model = service.ReferenceProject_Create('CustomArchitecture')
    service.Project_Save(model, reference, confirm_dangerous=True)
    board = service.catalog.Component_Get(model.board)
    inputs = root/'CubeMX_inputs'
    inputs.mkdir()
    for directory in ('Core', 'FATFS'):
        shutil.copytree(board.payload_root/directory, inputs/directory)
    shutil.copytree(reference/'Drivers', inputs/'Drivers')
    for pattern in ('*.s', '*.ld'):
        for source in reference.glob(pattern):
            shutil.copy2(source, inputs/source.name)
    for source in board.payload_root.glob('*.ioc'):
        shutil.copy2(source, inputs/source.name)
    imported = service.CubeMxProject_Import(inputs, model, risk_acknowledged=True)
    mapping = {item.resource_id: item.metadata['physical_resource']
               for item in BoardResourceProvisions_Get(board)}
    assert set(mapping.values()) <= {item.resource_id for item in imported.hardware.resources}
    assignments = {key: mapping[value] for key, value in model.resource_assignments.items()}
    model = replace(model, board='', hardware=imported.hardware, resource_assignments=assignments)
    model = service.ProjectConfiguration_Reconcile(model).model
    project = root/'custom'
    service.Project_Save(model, project, confirm_dangerous=True)
    assert not (project/'Board').exists()
    return project


def _Architecture_Run(project, name):
    result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', 'Tools/check_architecture.ps1'], cwd=project,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    (project/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
    return result


def test_complete_import_uses_actual_core_and_fatfs_paths(custom_architecture_project):
    result = _Architecture_Run(custom_architecture_project, 'valid_custom')
    assert result.returncode == 0, result.stdout+result.stderr


def test_imported_manifest_wildcards_are_still_rejected(custom_architecture_project):
    project = custom_architecture_project
    added = project/'HardwareGenerated/STM32CubeMX/unreviewed.mk'
    assert not added.exists()
    added.write_text('C_SOURCES += $(wildcard Core/Src/*.c)\n', encoding='utf-8')
    try:
        result = _Architecture_Run(project, 'invalid_imported_manifest')
        assert result.returncode != 0
        assert 'wildcard scanning or object flattening' in result.stdout
    finally:
        added.unlink()


def test_present_board_code_is_still_scanned_for_custom_projects(custom_architecture_project):
    project = custom_architecture_project
    added = project/'Board/unsafe.c'
    added.parent.mkdir(exist_ok=False)
    added.write_text('void Unsafe(void) { HAL_Unsafe(); }\n', encoding='utf-8')
    try:
        result = _Architecture_Run(project, 'invalid_board_code')
        assert result.returncode != 0
        assert 'Vendor types or MCU symbols leaked' in result.stdout
    finally:
        added.unlink()
        added.parent.rmdir()


def test_invalid_custom_snapshot_does_not_relax_scope(custom_architecture_project):
    project = custom_architecture_project
    path = project/'SilverStar.ssproject'
    original = path.read_bytes()
    configuration = json.loads(original)
    configuration['hardware']['snapshot_id'] = 'invalid'
    path.write_text(json.dumps(configuration), encoding='utf-8')
    try:
        result = _Architecture_Run(project, 'invalid_snapshot')
        assert result.returncode != 0
        assert 'Custom hardware requires an imported snapshot' in result.stdout
    finally:
        path.write_bytes(original)


def test_custom_ioc_path_cannot_escape_snapshot(custom_architecture_project):
    project = custom_architecture_project
    path = project/'SilverStar.ssproject'
    original = path.read_bytes()
    configuration = json.loads(original)
    configuration['hardware']['ioc_file'] = '../outside.ioc'
    path.write_text(json.dumps(configuration), encoding='utf-8')
    try:
        result = _Architecture_Run(project, 'invalid_ioc_path')
        assert result.returncode != 0
        assert 'Custom hardware IOC metadata must name one snapshot-local IOC file' in result.stdout
    finally:
        path.write_bytes(original)
