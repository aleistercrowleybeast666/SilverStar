"""Existing GUI actions for exact, isolated USB software candidates.

Receipts locate outputs; they never grant target admission or formal release.
"""
from copy import deepcopy
from pathlib import Path
from dataclasses import replace
import hashlib
import json
import os
import sys
import time
import uuid

from silverstar_fccg.app.native_ground import BINDING_KEY, NativeGroundBackendResult
from silverstar_fccg.app.usb_ground import (
    C071_PART, _Profile_Load, _Json_Encode,
    UsbGroundDeviceFacts_Get, UsbGroundTarget_Validate,
)
from silverstar_fccg.build.runner import BuildAction, BuildResult, BuildRunner
from silverstar_fccg.core.task import TaskCancelledError
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImportError
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse


RELEASE_STATUS = 'USB software candidate; formal release BLOCKED'


RELEASE_NOTICE = (
    "USB software candidate only; formal release BLOCKED. "
    "Independent USB safety review: NO_PASSED_OUTCOME (not retried). "
    "Critical-contract acceptance, whole-program stack/WCET: NOT PROVEN. "
    "PCD/IRQ scheduling and physical USB behaviour: outside Host evidence. "
    "No hardware action is required or performed by this workflow."
)


def UsbGroundBound_Is(model):
    return BINDING_KEY in model.ground_target.hardware.inventory


def UsbGroundOptions_Get(part):
    UsbGroundTarget_Validate(part, 48_000_000 if part == C071_PART else 72_000_000)
    profile = _Profile_Load('c071-device-facts.json' if part == C071_PART else 'f103-device-facts.json')
    # Backend-pinned bytes and IRQ enums are checked again on every operation.
    # An explicit SDK override is a location, never a new trust descriptor.
    header = Path(os.environ.get('SILVERSTAR_USB_SDK_' + ('C071' if part == C071_PART else 'F103'),
                                 profile['irq_evidence_source']))
    UsbGroundDeviceFacts_Get(part, header)
    options = {'independent_irq_header': header}
    if part == C071_PART:
        options['companion_root'] = Path(__file__).resolve().parents[3] / 'plugins/builtin/silverstar_usb_cdc_stm32c071_mini'
    return options


def UsbGroundFlow_Import(service, source, model, context):
    context.Cancel_RaiseIfRequested()
    root, ioc = service.hardware_importer._Input_Resolve(Path(source))
    inventory = CubeMxInventory_Parse(ioc.read_text(encoding='utf-8-sig'))
    part = inventory.mcu_part
    options = UsbGroundOptions_Get(part)
    context.Progress_Report(0.1, 'status.task_running')
    gpio = (('RADIO_NSS', 'RADIO_RESET', 'RADIO_BUSY', 'RADIO_DIO1') if part == C071_PART else
            ('SPI_RADIO_NSS', 'RADIO_RST', 'RADIO_BUSY', 'RADIO_DIO1'))
    result = service.UsbGroundProject_Import(root, deepcopy(model), part=part,
        hclk_hz=48_000_000 if part == C071_PART else 72_000_000,
        spi_resource='SPI1', gpio_resources=gpio, risk_acknowledged=True, **options)
    context.Cancel_RaiseIfRequested()
    context.Progress_Report(0.95, 'status.task_running')
    return result


def _Pointer_Path(project):
    return WorkspacePolicy(project).Path_Resolve('.fccg/usb-candidate.json', allow_root=False)


def _Pointer_Save(project, model, result):
    WorkspacePolicy(project).Text_AtomicWrite('.fccg/usb-candidate.json', json.dumps({
        'model_sha256': hashlib.sha256(_Json_Encode(model.Dictionary_Get())).hexdigest(),
        'output': str(result.output), 'backend_receipt_sha256': result.receipt_sha256,
        'result': result.result.value, 'formal_release': False}, indent=2))


def UsbGroundOutput_Get(service, model, project, *, compiled=False):
    service.UsbGroundCandidate_Plan(model, **UsbGroundOptions_Get(model.ground_target.hardware.mcu))
    pointer = json.loads(_Pointer_Path(project).read_text(encoding='utf-8'))
    if not isinstance(pointer, dict) or pointer.get('model_sha256') != hashlib.sha256(_Json_Encode(model.Dictionary_Get())).hexdigest():
        raise CubeMxImportError('USB candidate belongs to another saved model; generate/build again')
    if (not isinstance(pointer, dict) or not isinstance(pointer.get('output'), str)
            or not isinstance(pointer.get('backend_receipt_sha256'), str)
            or pointer.get('result') not in {NativeGroundBackendResult.RenderedCandidate.value,
                                           NativeGroundBackendResult.CompiledCandidate.value}):
        raise CubeMxImportError('USB candidate pointer is incomplete; generate/build again')
    output = Path(pointer['output'])
    if output.absolute() != output or output.resolve() != output or output.is_symlink() or output.is_junction():
        raise CubeMxImportError('USB candidate output alias rejected')
    protected = (Path(project).resolve(), service.hardware_importer.cache_root.resolve())
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise CubeMxImportError('USB candidate output must remain disjoint')
    receipt = output / 'backend-receipt.json'
    if hashlib.sha256(receipt.read_bytes()).hexdigest() != pointer['backend_receipt_sha256']:
        raise CubeMxImportError('USB candidate backend receipt changed')
    backend = json.loads(receipt.read_text(encoding='utf-8'))
    if not isinstance(backend, dict) or backend.get('model_sha256') != pointer['model_sha256']:
        raise CubeMxImportError('USB candidate model receipt changed')
    policy = WorkspacePolicy(output)
    expected_status = ('RENDERED_NOT_COMPILED' if pointer['result'] == NativeGroundBackendResult.RenderedCandidate.value
                       else NativeGroundBackendResult.CompiledCandidate.value)
    if backend.get('status') != expected_status:
        raise CubeMxImportError('USB candidate outcome differs from its backend receipt')
    if pointer['result'] == NativeGroundBackendResult.RenderedCandidate.value:
        if not isinstance(backend.get('files_sha256'), dict):
            raise CubeMxImportError('USB rendered receipt lacks its generated file inventory')
        for relative, digest in backend['files_sha256'].items():
            if hashlib.sha256(policy.Path_Resolve(relative, allow_root=False).read_bytes()).hexdigest() != digest:
                raise CubeMxImportError('Rendered USB candidate changed: ' + relative)
        if compiled:
            raise CubeMxImportError('USB candidate is rendered, not compiled; build first')
    elif pointer['result'] == NativeGroundBackendResult.CompiledCandidate.value:
        if not isinstance(backend.get('compile_receipt_sha256'), str):
            raise CubeMxImportError('USB backend receipt lacks its compiler identity')
        compilation = output / 'receipt.json'
        if hashlib.sha256(compilation.read_bytes()).hexdigest() != backend['compile_receipt_sha256']:
            raise CubeMxImportError('USB compiler receipt changed')
        record = json.loads(compilation.read_text(encoding='utf-8'))
        if (not isinstance(record, dict) or record.get('status') != 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
                or record.get('runtime_model_sha256') != pointer['model_sha256']
                or any(not isinstance(record.get(key), dict) for key in
                       ('experimental_files_sha256', 'output_artifact_sha256', 'input_sha256'))):
            raise CubeMxImportError('USB compiler result is not an exact-model software success')
        for relative, digest in {**record['experimental_files_sha256'], **record['output_artifact_sha256']}.items():
            if hashlib.sha256(policy.Path_Resolve(relative, allow_root=False).read_bytes()).hexdigest() != digest:
                raise CubeMxImportError('USB candidate source/artifact changed: ' + relative)
        # Copied native inputs must still equal the admitted input bytes.
        prefix = 'HardwareGenerated/STM32CubeMX/'
        from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX
        if model.ground_target.hardware.mcu != C071_PART:
            prefix = NATIVE_PREFIX
        for relative, digest in record['input_sha256'].items():
            if hashlib.sha256(policy.Path_Resolve(prefix + relative, allow_root=False).read_bytes()).hexdigest() != digest:
                raise CubeMxImportError('USB copied native input changed: ' + relative)
    else:
        raise CubeMxImportError('USB candidate has no successful rendered/compiled outcome')
    return output


def UsbGroundFlow_Run(service, model, project, operation, context):
    model = deepcopy(model)
    context.Cancel_RaiseIfRequested()
    options = UsbGroundOptions_Get(model.ground_target.hardware.mcu)
    service.UsbGroundCandidate_Plan(model, **options)
    context.Line_Report(RELEASE_NOTICE)
    if operation not in {'generate', 'build'}:
        raise ValueError('Unknown USB candidate operation')
    service.ProjectRoot_Save(model, Path(project))
    context.Cancel_RaiseIfRequested()
    # Fresh sibling output: never overwrite the user's native tree or project.
    output = Path(project).resolve().parent / ('usb-' + uuid.uuid4().hex[:12])
    if operation == 'generate':
        context.Progress_Report(0.15, 'status.generation_running')
        result = service.UsbGroundCandidate_Export(model, output, task_context=context, **options)
    else:
        result = service.UsbGroundCandidate_Build(model, Path(project), output, task_context=context, **options)
    context.Cancel_RaiseIfRequested()
    if result.result == NativeGroundBackendResult.FailedCandidate:
        raise CubeMxImportError(result.detail + '; receipt: ' + str(result.receipt))
    _Pointer_Save(project, model, result)
    context.Line_Report(f'USB {result.result.value}: {result.output}; backend receipt {result.receipt_sha256}')
    context.Progress_Report(0.99, 'status.task_running')
    return result


def UsbGroundQualityHash_Get(service, model, project, action):
    output = UsbGroundOutput_Get(service, model, project, compiled=action in {'artifact_check', 'static_analysis'})
    pointer = json.loads(_Pointer_Path(project).read_text(encoding='utf-8'))
    digest = hashlib.sha256(_Json_Encode([pointer, action]))
    for path in sorted((output / 'Tools').rglob('*')):
        if path.is_file():
            digest.update(str(path.relative_to(output)).encode())
            digest.update(WorkspacePolicy(output).Path_Resolve(path, allow_root=False).read_bytes())
    return output, digest.hexdigest()


def UsbGroundQuality_Run(service, model, project, action, context):
    from silverstar_fccg.build.quality_batch import TargetQualityResult
    started = time.perf_counter()
    output = Path(project)
    result = None
    digest = ''
    error = ''
    try:
        output, before = UsbGroundQualityHash_Get(service, model, project, action.value)
        checker = 'check_c071_candidate.py' if model.ground_target.hardware.mcu == C071_PART else 'check_native_ground.py'
        selected = deepcopy(model)
        selected.build = replace(selected.ground_target.build, tool_paths={
            **model.build.tool_paths, **selected.ground_target.build.tool_paths})
        runner = BuildRunner(WorkspacePolicy(output))
        environment = runner._Environment_Get(selected, action)
        python = environment.get('PYTHON', sys.executable)
        command = (python, 'Tools/' + checker)
        if action == BuildAction.HOST_TESTS:
            host = runner._HostCompiler_Resolve(selected)
            if host is None:
                raise ValueError('Host C compiler unavailable')
            command += ('host', '--host-cc', str(host))
        elif action in {BuildAction.ARTIFACT_CHECK, BuildAction.STATIC_ANALYSIS}:
            command += ('artifact', '--prefix', selected.build.toolchain_prefix)
        elif action == BuildAction.POWER10_CHECK:
            command = ('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                       'Tools/check_power_of_ten.ps1', '-TargetKind', 'Ground')
        elif action != BuildAction.ARCHITECTURE_CHECK:
            raise ValueError('Unknown USB software check')
        context.Line_Report(RELEASE_NOTICE)
        code, lines = runner._Process_Run(command, output, environment, context, context.Line_Report)
        context.Cancel_RaiseIfRequested()
        _, digest = UsbGroundQualityHash_Get(service, model, project, action.value)
        if digest != before:
            raise CubeMxImportError('USB quality inputs changed during check')
        result = BuildResult(action, command, code, RELEASE_NOTICE + '\n' + ''.join(lines), live_streamed=True)
    except TaskCancelledError:
        raise
    except Exception as exception:
        error = str(exception)
    return TargetQualityResult('ground', output, model, result, digest, time.perf_counter() - started, error)
