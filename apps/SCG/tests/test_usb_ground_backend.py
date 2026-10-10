"""Normal first-batch model/recipe binding; no USB packet or owner research."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import pytest

from test_native_ground_backend import bound as legacy_bound
from test_native_classic_cdc import native
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.usb_ground import (
    C071_KEY, C071_PART, UsbGroundDeviceFacts_Get, UsbGroundTarget_Validate, UsbGroundPlanResult,
)
from silverstar_fccg.app.native_ground import BINDING_KEY, NativeGroundBackendResult
from silverstar_fccg.build.runner import BuildAction
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.generator.multi_target import GroundFiles_Render
from silverstar_fccg.hardware.cubemx import CubeMxImportError, CubeMxImporter
from silverstar_fccg.project.model import ProjectModel_Load


@pytest.fixture
def bound(native, tmp_path_factory, builtin_catalog):
    """Unified positive flows use the unified authority, not a legacy fixture."""
    source, args = native
    service = FccgService(tmp_path_factory.mktemp('w'))
    service.catalog = builtin_catalog
    model = ProjectModel_Load(Path(os.environ['SILVERSTAR_NATIVE_BACKEND_CONFIG']))
    facts = args['device_facts']
    if facts.part == 'STM32F407VET6':
        imported = service.NativeClassicCdcGroundProject_Import(source, model,
            **args, hclk_hz=168_000_000, risk_acknowledged=True)
    else:
        header = Path(facts.irq_evidence_source)
        imported = service.UsbGroundProject_Import(source, model,
            part=facts.part, independent_irq_header=header, hclk_hz=72_000_000,
            spi_resource=args['spi_resource'], gpio_resources=args['gpio_resources'],
            risk_acknowledged=True)
        args = {**args, 'device_facts': UsbGroundDeviceFacts_Get(facts.part, header)}
    return service, imported, args, source


@pytest.mark.parametrize('native', ['f103-usb'], indirect=True)
def test_legacy_authority_requires_reimport_without_relabeling(legacy_bound, tmp_path_factory):
    from silverstar_fccg.app.usb_ground import F103_REIMPORT_REQUIRED, UsbGroundReimportIssue_Get
    from silverstar_fccg.app.usb_ground_flow import UsbGroundBound_Is
    service, imported, args, source = legacy_bound
    facts = args['device_facts']
    assert facts.part == 'STM32F103C8T6'
    before = deepcopy(imported.model.Dictionary_Get())
    assert UsbGroundBound_Is(imported.model)
    assert UsbGroundReimportIssue_Get(imported.model) == F103_REIMPORT_REQUIRED
    assert service.NativeClassicCdcGroundCandidate_Plan(imported.model,
        device_facts=facts).profile == 'f103-systick-classic-v1'
    header = Path(facts.irq_evidence_source)
    output = tmp_path_factory.mktemp('o') / 'not-created'
    with pytest.raises(CubeMxImportError, match='F103_UNIFIED_REIMPORT_REQUIRED'):
        service.UsbGroundCandidate_Export(imported.model, output, independent_irq_header=header)
    assert not output.exists()
    assert imported.model.Dictionary_Get() == before
    rebound = service.UsbGroundProject_Import(source, imported.model, part=facts.part,
        independent_irq_header=header, hclk_hz=72_000_000,
        spi_resource=args['spi_resource'], gpio_resources=args['gpio_resources'], risk_acknowledged=True)
    assert not UsbGroundReimportIssue_Get(rebound.model)
    assert rebound.model.Dictionary_Get() != before
    assert service.UsbGroundCandidate_Plan(rebound.model,
        independent_irq_header=header).result == UsbGroundPlanResult.RenderedCandidate


@pytest.fixture
def c071(tmp_path_factory, builtin_catalog):
    source = Path(os.environ['SILVERSTAR_C071_NATIVE'])
    companion = Path(os.environ['SILVERSTAR_C071_COMPANION'])
    header = Path(os.environ['SILVERSTAR_C071_SDK_HEADER'])
    service = FccgService(tmp_path_factory.mktemp('u'))
    service.hardware_importer = CubeMxImporter(service.policy, service.workspace_root / 'i')
    service.catalog = builtin_catalog
    model = ProjectModel_Load(Path(os.environ['SILVERSTAR_NATIVE_BACKEND_CONFIG']))
    before = deepcopy(model.Dictionary_Get())
    result = service.UsbGroundProject_Import(source, model, part=C071_PART,
        independent_irq_header=header, hclk_hz=48_000_000, spi_resource='SPI1',
        gpio_resources=('RADIO_NSS','RADIO_RESET','RADIO_BUSY','RADIO_DIO1'),
        risk_acknowledged=True, companion_root=companion)
    assert before == model.Dictionary_Get()
    return service, result, header, companion, source


def test_c071_save_reload_recipe_and_source_preservation(c071, tmp_path_factory):
    service, result, header, companion, source = c071
    hashes = {p: hashlib.sha256((source / p).read_bytes()).hexdigest()
        for p in result.model.ground_target.hardware.inventory[C071_KEY]['native_files_sha256']}
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(result.model, project, create_new=True)
    model = ProjectModel_Load(project / 'SilverStar.ssproject')
    reloaded = FccgService(service.workspace_root)
    reloaded.hardware_importer = CubeMxImporter(reloaded.policy, service.hardware_importer.cache_root)
    reloaded.catalog = service.catalog
    plan = reloaded.UsbGroundCandidate_Plan(model, independent_irq_header=header, companion_root=companion)
    assert plan.result == UsbGroundPlanResult.RenderedCandidate
    assert plan.native_plan is not None
    assert plan.capability_facts == {'native_pcd': True, 'native_classic_cdc': False,
        'companion_source_identity_verified': True, 'cdc_runtime_accepted': False, 'formal_release': False}
    assert plan.source_snapshot_id == result.imported.hardware.snapshot_id
    assert plan.model_sha256 == hashlib.sha256(json.dumps(model.Dictionary_Get(), sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    assert plan.recipe_plan['firmware_files_rendered'] is True
    assert 'HardwareGenerated/STM32CubeMX/Core/Src/usb.c' in plan.recipe_plan['effective_build_to_integrate']['build_sources']
    assert 'HardwareGenerated/STM32CubeMX/startup_stm32c071xx.s' in plan.recipe_plan['effective_build_to_integrate']['asm_sources']
    assert model.ground_target.hardware.capabilities == ('usb.native_pcd',)
    assert hashes == {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in hashes}
    assert not any((project / 'Ground_Station').iterdir())


@pytest.mark.parametrize('change', ['part', 'profile', 'release', 'capability', 'source_graph', 'resource', 'risk'])
def test_c071_bound_model_changes_are_not_authority(c071, change):
    service, result, header, companion, _source = c071
    model = deepcopy(result.model)
    hardware = model.ground_target.hardware
    if change == 'part':
        hardware = replace(hardware, mcu='STM32C071RBT6')
    elif change == 'profile':
        hardware.inventory[BINDING_KEY]['profile'] = 'C071_ALL'
    elif change == 'release':
        hardware.inventory[BINDING_KEY]['formal_generation'] = 'ENABLED'
    elif change == 'capability':
        hardware = replace(hardware, capabilities=('usb.cdc',))
    elif change == 'source_graph':
        hardware = replace(hardware, build_sources=())
    elif change == 'resource':
        model.ground_target = replace(model.ground_target, resource_assignments={'radio0:spi':'SPI2'})
    else:
        hardware = replace(hardware, risk_acknowledged=False)
    model.ground_target = replace(model.ground_target, hardware=hardware)
    with pytest.raises(CubeMxImportError):
        service.UsbGroundCandidate_Plan(model, independent_irq_header=header, companion_root=companion)


def test_c071_all_output_routes_block_before_write(c071, tmp_path_factory):
    service, result, header, companion, _source = c071
    model = result.model
    project = tmp_path_factory.mktemp('p')
    service.ProjectRoot_Save(model, project, create_new=True)
    output = tmp_path_factory.mktemp('o') / 'candidate'
    exported=service.UsbGroundCandidate_Export(model,output,independent_irq_header=header,companion_root=companion)
    assert exported.result == NativeGroundBackendResult.RenderedCandidate
    assert (output/'Generated/ground_source_graph.json').is_file()
    with pytest.raises(CubeMxImportError,match='new|disjoint|exist'):
        service.UsbGroundCandidate_Build(model,project,output,independent_irq_header=header,companion_root=companion)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.GenerationPlan_Create(model, project)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.Project_EnsureBuildable(model, project)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.GenerationPlan_Apply(model, None)
    with pytest.raises(FccgError, match='formal build remains blocked'):
        service.Build_Run(model, project, BuildAction.BUILD, ensure_buildable=False)
    with pytest.raises(ValueError, match='Normal firmware generation is blocked'):
        GroundFiles_Render(model, service.catalog, service.policy)


def test_c071_cache_changes_preserved_and_refused(c071):
    service, result, header, companion, _source = c071
    path = result.imported.snapshot_root / 'Core/Inc/main.h'
    body = path.read_bytes() + b'\n/* local ordinary edit */\n'
    path.write_bytes(body)
    with pytest.raises(CubeMxImportError, match='identity changed'):
        service.UsbGroundCandidate_Plan(result.model, independent_irq_header=header, companion_root=companion)
    assert path.read_bytes() == body


def test_missing_companion_and_project_local_facts_rejected(c071):
    service, result, header, _companion, _source = c071
    with pytest.raises(CubeMxImportError, match='pinned external companion'):
        service.UsbGroundCandidate_Plan(result.model, independent_irq_header=header)
    local = result.imported.snapshot_root / 'Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h'
    with pytest.raises(CubeMxImportError, match='outside'):
        service.UsbGroundCandidate_Plan(result.model, independent_irq_header=local)


@pytest.mark.parametrize('part,clock', [('STM32F407VET6',168_000_000),('STM32C071RBT6',48_000_000),
    ('STM32F103CBT6',72_000_000),('STM32C071FBP6',True),('STM32F103C8T6',48_000_000)])
def test_first_batch_exact_device_clock_rejection(part, clock):
    with pytest.raises(CubeMxImportError):
        UsbGroundTarget_Validate(part, clock)


def test_independent_c071_sdk_irq_and_memory_facts():
    header = Path(os.environ['SILVERSTAR_C071_SDK_HEADER'])
    facts = UsbGroundDeviceFacts_Get(C071_PART, header)
    assert facts.core == 'cortex-m0plus' and facts.fpu == ''
    assert len(facts.irq_numbers) == 31
    assert ('USB_DRD_FS_IRQn',8) in facts.irq_numbers
    assert facts.regions[0].length == 131072 and facts.regions[1].length == 24576


def test_f103_dispatch_reuses_plan_f407_stays_private(bound):
    service, imported, args, _source = bound
    facts = args['device_facts']
    if facts.part == 'STM32F407VET6':
        with pytest.raises(CubeMxImportError, match='Unsupported first-batch'):
            service.UsbGroundCandidate_Plan(imported.model, independent_irq_header=Path(facts.irq_evidence_source))
        old = service.NativeClassicCdcGroundCandidate_Plan(imported.model, device_facts=facts)
        assert old.profile == 'f407-tim1-indexed-v1'
    else:
        rebound = service.UsbGroundProject_Import(_source, imported.model, part=facts.part,
            independent_irq_header=Path(facts.irq_evidence_source), hclk_hz=72_000_000,
            spi_resource=args['spi_resource'], gpio_resources=args['gpio_resources'], risk_acknowledged=True)
        assert rebound.model.Dictionary_Get() == imported.model.Dictionary_Get()
        plan = service.UsbGroundCandidate_Plan(rebound.model, independent_irq_header=Path(facts.irq_evidence_source))
        old = service.NativeClassicCdcGroundCandidate_Plan(imported.model, device_facts=facts)
        assert plan.result == UsbGroundPlanResult.RenderedCandidate
        assert plan.native_plan.files == old.files and plan.model_sha256 == old.model_sha256
        assert plan.capability_facts['formal_release'] is False


def test_real_unified_backend_build_exact_first_batch(bound, tmp_path_factory):
    assert os.environ.get('SILVERSTAR_USB_BACKEND_ARM') == '1'
    service, imported, args, _source = bound
    facts = args['device_facts']
    project = tmp_path_factory.mktemp('p')
    output = tmp_path_factory.mktemp('o') / 'b'
    service.ProjectRoot_Save(imported.model, project, create_new=True)
    if facts.part == 'STM32F407VET6':
        with pytest.raises(CubeMxImportError, match='Unsupported first-batch'):
            service.UsbGroundCandidate_Build(imported.model, project, output,
                independent_irq_header=Path(facts.irq_evidence_source))
        assert not output.exists()
        return
    exported = service.UsbGroundCandidate_Export(imported.model, tmp_path_factory.mktemp('o') / 'r',
        independent_irq_header=Path(facts.irq_evidence_source))
    assert exported.result == NativeGroundBackendResult.RenderedCandidate
    result = service.UsbGroundCandidate_Build(imported.model, project, output,
        independent_irq_header=Path(facts.irq_evidence_source))
    assert result.result == NativeGroundBackendResult.CompiledCandidate, result.detail
    compiler = json.loads((output / 'receipt.json').read_text(encoding='utf-8'))
    backend = json.loads(result.receipt.read_text(encoding='utf-8'))
    assert compiler['runtime_model_sha256'] == backend['model_sha256']
    assert compiler['facts']['part'] == 'STM32F103C8T6'
    assert compiler['warning_diagnostics'] == []
    with Path(os.environ['SILVERSTAR_USB_BACKEND_BUILD_INDEX']).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'part':facts.part,'output':str(output),'project':str(project),
            'backend_receipt_sha256':result.receipt_sha256}) + '\n')


def test_real_c071_unified_build(c071,tmp_path_factory):
    assert os.environ.get('SILVERSTAR_USB_BACKEND_ARM')=='1'
    service,result,header,companion,_source=c071
    project=tmp_path_factory.mktemp('p');output=tmp_path_factory.mktemp('o')/'b'
    service.ProjectRoot_Save(result.model,project,create_new=True)
    built=service.UsbGroundCandidate_Build(result.model,project,output,independent_irq_header=header,companion_root=companion)
    if os.environ.get('SILVERSTAR_USB_BACKEND_BUILD_INDEX'):
        with Path(os.environ['SILVERSTAR_USB_BACKEND_BUILD_INDEX']).open('a',encoding='utf8') as stream:
            stream.write(json.dumps({'part':'STM32C071FBP6','output':str(output),'result':built.result.value,
                'project_root':str(project.resolve()),'runtime_project':str((project/'SilverStar.ssproject').resolve()),
                'snapshot_root':str((service.hardware_importer.cache_root/result.model.ground_target.hardware.snapshot_id/'UsbGroundNative').resolve()),
                'backend_receipt_sha256':built.receipt_sha256,'compile_receipt_sha256':hashlib.sha256((output/'receipt.json').read_bytes()).hexdigest() if (output/'receipt.json').is_file() else None})+'\n')
    assert built.result == NativeGroundBackendResult.CompiledCandidate,built.detail
    receipt=json.loads((output/'receipt.json').read_text())
    assert receipt['facts']['core']=='cortex-m0plus' and not receipt['warning_diagnostics']
    assert receipt['graph']['formal_release'] is False
    backend=json.loads(built.receipt.read_text())
    assert backend['project_root']==str(project.resolve())
    assert backend['runtime_project']==str((project/'SilverStar.ssproject').resolve())
    assert backend['runtime_project_sha256']==hashlib.sha256((project/'SilverStar.ssproject').read_bytes()).hexdigest()
    assert Path(backend['snapshot_root']).is_dir()
