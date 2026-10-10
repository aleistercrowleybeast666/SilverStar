"""Normal backend import/model/render/build flow; no USB packet/owner research."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import shutil
import pytest

from test_native_classic_cdc import native
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.native_ground import BINDING_KEY, NativeGroundBackendResult
from silverstar_fccg.build.runner import BuildAction
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import GroundFiles_Render
from silverstar_fccg.hardware.cubemx import CubeMxImportError
from silverstar_fccg.project.model import ProjectModel_Load


@pytest.fixture
def bound(native, tmp_path_factory, builtin_catalog):
    root, args = native
    service = FccgService(tmp_path_factory.mktemp('w'))
    service.catalog = builtin_catalog
    model = ProjectModel_Load(Path(os.environ['SILVERSTAR_NATIVE_BACKEND_CONFIG']))
    original = deepcopy(model.Dictionary_Get())
    hclk = 72_000_000 if args['device_facts'].part == 'STM32F103C8T6' else 168_000_000
    result = service.NativeClassicCdcGroundProject_Import(root, model, **args,
        hclk_hz=hclk, risk_acknowledged=True)
    assert model.Dictionary_Get() == original
    assert result.result == NativeGroundBackendResult.ImportedCandidate
    return service, result, args, root


def test_backend_import_save_reload_render_normal_flow(bound, tmp_path_factory):
    service, imported, args, original_root = bound
    model = imported.model
    before = {p.relative_to(original_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in original_root.rglob('*') if p.is_file()}
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(model, project, create_new=True)
    loaded = ProjectModel_Load(project / 'SilverStar.ssproject')
    assert loaded.Dictionary_Get() == model.Dictionary_Get()
    assert loaded.ground_target.mcu == loaded.ground_target.board == ''
    assert loaded.ground_target.resource_assignments['radio0:spi'] == 'SPI1'
    assert loaded.ground_target.hardware.inventory[BINDING_KEY]['facts_sha256']
    # Reload in another service instance with the same backend cache, not CLI args.
    reloaded = FccgService(service.workspace_root)
    reloaded.catalog = service.catalog
    plan = reloaded.NativeClassicCdcGroundCandidate_Plan(loaded, device_facts=args['device_facts'])
    assert plan.profile == imported.profile
    assert plan.snapshot_id == imported.imported.hardware.snapshot_id
    assert 'NativeRuntime_Init' in plan.files['Generated/Src/native_runtime.c'].decode()
    assert plan.contract['publication'].startswith('PRIVATE CANDIDATE ONLY')
    assert 'NOT PROVEN' in plan.contract['ep0_review']
    output = tmp_path_factory.mktemp('o') / 'r'
    result = reloaded.NativeClassicCdcGroundCandidate_Export(loaded, output, device_facts=args['device_facts'])
    assert result.result == NativeGroundBackendResult.RenderedCandidate
    receipt = json.loads(result.receipt.read_text())
    assert receipt['status'] == 'RENDERED_NOT_COMPILED'
    assert receipt['model_sha256'] == plan.model_sha256
    assert receipt['files_sha256'] == {p: hashlib.sha256((output / p).read_bytes()).hexdigest() for p in plan.files}
    assert result.receipt_sha256 == hashlib.sha256(result.receipt.read_bytes()).hexdigest()
    assert before == {p.relative_to(original_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in original_root.rglob('*') if p.is_file()}
    assert not any((project / 'Ground_Station').iterdir())
    with pytest.raises(ValueError, match='Normal firmware generation is blocked'):
        GroundFiles_Render(loaded, service.catalog, service.policy)


def test_formal_build_rejects_even_without_ensure_buildable(bound, tmp_path_factory, monkeypatch):
    service, imported, _args, _root = bound
    class ForbiddenRunner:
        def __init__(self, *_args):
            raise AssertionError('Formal build runner must not be created')
    monkeypatch.setattr('silverstar_fccg.app.service.BuildRunner', ForbiddenRunner)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.Build_Run(imported.model, tmp_path_factory.mktemp('p'), BuildAction.BUILD,
            ensure_buildable=False)


@pytest.mark.parametrize('change', ['facts', 'profile', 'source-graph', 'resource', 'clock', 'release-flag'])
def test_bound_project_mismatch_rejected_before_output(bound, tmp_path_factory, change):
    service, imported, args, _root = bound
    model = deepcopy(imported.model)
    facts = args['device_facts']
    if change == 'facts':
        facts = replace(facts, evidence_sha256='0' * 64)
    elif change == 'profile':
        model.ground_target.hardware.inventory[BINDING_KEY]['profile'] = 'generic-stm32'
    elif change == 'source-graph':
        model.ground_target = replace(model.ground_target,
            hardware=replace(model.ground_target.hardware, build_sources=()))
    elif change == 'resource':
        model.ground_target = replace(model.ground_target, resource_assignments={'radio0:spi': 'SPI2'})
    elif change == 'clock':
        model.ground_target.hardware.inventory[BINDING_KEY]['hclk_hz'] = 1
    else:
        model.ground_target.hardware.inventory[BINDING_KEY]['formal_generation'] = 'ENABLED'
    output = tmp_path_factory.mktemp('o') / 'r'
    with pytest.raises(CubeMxImportError):
        service.NativeClassicCdcGroundCandidate_Export(model, output, device_facts=facts)
    assert not output.exists()


def test_unknown_device_and_unacknowledged_import_preserve_model(native, tmp_path_factory, builtin_catalog):
    root, args = native
    service = FccgService(tmp_path_factory.mktemp('w'))
    service.catalog = builtin_catalog
    model = ProjectModel_Load(Path(os.environ['SILVERSTAR_NATIVE_BACKEND_CONFIG']))
    before = deepcopy(model.Dictionary_Get())
    hclk = 72_000_000 if args['device_facts'].part == 'STM32F103C8T6' else 168_000_000
    with pytest.raises(CubeMxImportError, match='Unsupported native Ground device/clock profile'):
        service.NativeClassicCdcGroundProject_Import(root, model,
            **{**args, 'device_facts': replace(args['device_facts'], part='STM32F429VIT6')},
            hclk_hz=hclk, risk_acknowledged=True)
    with pytest.raises(CubeMxImportError, match='acknowledgement'):
        service.NativeClassicCdcGroundProject_Import(root, model, **args,
            hclk_hz=hclk, risk_acknowledged=False)
    assert model.Dictionary_Get() == before
    assert not service.hardware_importer.cache_root.exists()


def test_changed_snapshot_preserved_and_refused(bound, tmp_path_factory):
    service, imported, args, _root = bound
    source = imported.imported.snapshot_root / 'Core/Inc/main.h'
    old = source.read_bytes()
    source.write_bytes(old + b'\n/* local edit */\n')
    output = tmp_path_factory.mktemp('o') / 'r'
    with pytest.raises(CubeMxImportError, match='modified'):
        service.NativeClassicCdcGroundCandidate_Export(imported.model, output, device_facts=args['device_facts'])
    assert source.read_bytes() == old + b'\n/* local edit */\n'
    assert not output.exists()


def test_existing_output_and_unsaved_project_not_overwritten(bound, tmp_path_factory):
    service, imported, args, _root = bound
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(imported.model, project, create_new=True)
    output = tmp_path_factory.mktemp('o')
    (output / 'user.txt').write_text('retain me')
    with pytest.raises(CubeMxImportError, match='new unaliased output'):
        service.NativeClassicCdcGroundCandidate_Export(imported.model, output, device_facts=args['device_facts'])
    assert (output / 'user.txt').read_text() == 'retain me'
    unsaved = deepcopy(imported.model)
    unsaved.identity = replace(unsaved.identity, name=unsaved.identity.name + '-unsaved')
    fresh = tmp_path_factory.mktemp('o') / 'b'
    with pytest.raises(CubeMxImportError, match='Save the exact bound native project'):
        service.NativeClassicCdcGroundCandidate_Build(unsaved, project, fresh, device_facts=args['device_facts'])
    assert not fresh.exists()
    with pytest.raises(CubeMxImportError, match='disjoint'):
        service.NativeClassicCdcGroundCandidate_Build(imported.model, project,
            project / 'Ground_Station' / 'candidate', device_facts=args['device_facts'])
    assert not (project / 'Ground_Station' / 'candidate').exists()


def test_compile_failure_is_not_reported_as_candidate_success(bound, tmp_path_factory, monkeypatch):
    service, imported, args, _root = bound
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(imported.model, project, create_new=True)
    output = tmp_path_factory.mktemp('o') / 'b'
    def failed(args, **kwargs):
        args.output.mkdir()
        (args.output / 'backend-owner.json').write_text(json.dumps({'token': args.backend_owner_token}))
        (args.output / 'receipt.json').write_text(json.dumps({'status': 'FAILED'}))
        raise ValueError('normal compiler unavailable')
    monkeypatch.setattr('silverstar_fccg.build.native_compile.NativeCompile_Run', failed)
    result = service.NativeClassicCdcGroundCandidate_Build(imported.model, project, output,
        device_facts=args['device_facts'])
    assert result.result == NativeGroundBackendResult.FailedCandidate
    receipt = json.loads(result.receipt.read_text())
    assert receipt['failure'] == 'normal compiler unavailable'
    assert receipt['compile_receipt_sha256'] == hashlib.sha256((output / 'receipt.json').read_bytes()).hexdigest()
    assert receipt['status'] != NativeGroundBackendResult.CompiledCandidate


def test_real_backend_bound_build_receipt(bound, tmp_path_factory):
    if os.environ.get('SILVERSTAR_NATIVE_BACKEND_ARM') != '1':
        pytest.skip('Explicit real ARM/analyzer backend flow execution not requested')
    assert shutil.which('arm-none-eabi-gcc')
    service, imported, args, _root = bound
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(imported.model, project, create_new=True)
    loaded = ProjectModel_Load(project / 'SilverStar.ssproject')
    output = tmp_path_factory.mktemp('o') / 'b'
    result = service.NativeClassicCdcGroundCandidate_Build(loaded, project, output,
        device_facts=args['device_facts'])
    assert result.result == NativeGroundBackendResult.CompiledCandidate, result.detail
    backend = json.loads(result.receipt.read_text())
    compiler = json.loads((output / 'receipt.json').read_text())
    assert backend['failure'] is None
    assert compiler['status'] == 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert compiler['validation_scope'] == 'PRIVATE_NATIVE_GROUND_RUNTIME_CANDIDATE'
    assert compiler['facts']['part'] == args['device_facts'].part
    assert compiler['warning_diagnostics'] == []
    assert (output / 'build/native.elf').is_file()
    assert (output / 'build/analysis/native.elf').is_file()
    assert json.loads((output / 'candidate_config.ssproject').read_text()) == loaded.Dictionary_Get()
    assert backend['compile_receipt_sha256'] == hashlib.sha256((output / 'receipt.json').read_bytes()).hexdigest()
    assert 'NOT PROVEN' in backend['limits']
    index = os.environ.get('SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX')
    if index:
        with Path(index).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'part': args['device_facts'].part, 'output': str(output),
                'project': str(project), 'backend_receipt_sha256': result.receipt_sha256,
                'snapshot_root': str(imported.imported.snapshot_root)}) + '\n')


def test_formal_plan_and_generation_reject_bound_model(bound, tmp_path_factory):
    service, imported, _args, _root = bound
    project = tmp_path_factory.mktemp('p')
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.GenerationPlan_Create(imported.model, project)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.Project_EnsureBuildable(imported.model, project)
    # Removing the static admission marker does not turn bound metadata into
    # approval or send this project to the legacy renderer.
    modified = deepcopy(imported.model)
    modified.ground_target.hardware.inventory.pop('native_complete_classic_cdc')
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.Build_Run(modified, project, BuildAction.BUILD, ensure_buildable=False)
    assert not any(project.iterdir())
