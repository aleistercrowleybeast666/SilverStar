"""Private C071 model conversion and ordinary recipe, preserving native ownership."""
from copy import deepcopy
from dataclasses import replace
import hashlib, json
from silverstar_fccg.hardware.c071_mini import C071Native_Validate, C071PadIdentity_Get
from silverstar_fccg.hardware.cubemx_ground import GroundCubeInputs_Get
from silverstar_fccg.generator.c071_recipe import C071Recipe_Render
from silverstar_fccg.generator.native_no_heap import NativeNoHeap_FilesRender

def C071Candidate_Render(native, inventory, model, catalog, snapshot, profile):
    inputs=GroundCubeInputs_Get(snapshot, 'STM32C071FBP6')
    companion=C071Native_Validate(snapshot)
    from silverstar_fccg.project.model import HardwareResource
    resources=inventory.HardwareResources_Get()+(HardwareResource('USB_CDC','usb_cdc',{
        'capabilities':['usb.device','usb.cdc'],
        'physical_resource':'C071 USB Device classic CDC companion',
        'pins':{'dm':'PA11','dp':'PA12'},'interrupt':'USB_DRD_FS_IRQn',
        'source_kind':'registered_companion','companion_profile':companion['profile'],'native_cdc':False}),)
    data=inventory.Dictionary_Get()
    data.update(ground_cubemx_base={'format_version':1,'mcu_flags':list(inputs.flags),
        'required_irq_handlers':list(inputs.irq_handlers), 'build_manifest':'Makefile',
        'artifact_hashes':{p:hashlib.sha256(b).hexdigest() for p,b in native.items()}},
        native_usb_cdc=data['usb_cdc'],usb_cdc=True,c071_companion=companion,
        package_pad_identity=C071PadIdentity_Get(native[model.ground_target.hardware.ioc_file].decode('utf8')))
    build=profile['effective_build']
    hardware=replace(model.ground_target.hardware, inventory=data, resources=resources,
        capabilities=tuple(sorted({'peripheral.'+r.kind for r in resources})),
        build_sources=tuple(build['build_sources']),include_dirs=tuple(build['include_dirs']),
        asm_sources=tuple(build['asm_sources']),defines=tuple(build['defines']),linker_script=build['linker_script'])
    internal=deepcopy(model)
    roles={'radio_bus':'SPI1','radio_nss':'RADIO_NSS','radio_reset':'RADIO_RESET',
        'radio_busy':'RADIO_BUSY','radio_dio1':'RADIO_DIO1','time':'SYSTEM_TIME'}
    internal.ground_target=replace(internal.ground_target,mcu='silverstar.mcu.stm32c071fbp6',
        hardware=hardware,pc_resource='USB_CDC',resource_assignments={'radio0:'+k:v for k,v in roles.items()})
    files=C071Recipe_Render(internal,catalog,native)
    files.update(NativeNoHeap_FilesRender(native['Core/Src/sysmem.c']))
    from pathlib import Path
    files['Tools/native_machine_contract.py']=(Path(__file__).resolve().parents[1]/'hardware/native_machine_contract.py').read_bytes()
    graph=json.loads(files['Generated/ground_source_graph.json'])
    from silverstar_fccg.generator.c071_lifecycle import C071Lifecycle_Integrate
    lifecycle=C071Lifecycle_Integrate(files,graph)
    graph['sources'].append('Generated/Src/native_no_heap.c')
    # Reuse the existing bare-metal single radio owner repair. DIO ISR only
    # records a flag; tick and USB must remain live during radio SPI/Busy waits.
    from silverstar_fccg.generator.native_radio import NativeRadioHal_Derive,NativeRadioDevice_Derive
    import difflib
    payload_derivatives=[]
    radio_hal='Devices/Telemetry/SX1281/Hal/sx1280-hal.c'
    candidates=[p for p in files if p.endswith('/sx1280-hal.c')]
    if len(candidates)!=1:raise ValueError('C071 radio HAL owner is not unique')
    radio_hal=candidates[0]
    for original,derived,transform in (
        (radio_hal,'HardwareGenerated/ReviewedC071Radio/'+radio_hal,
         lambda body:NativeRadioHal_Derive(body,context_header='c071_context.h',context_expression='C071MainContext_AllowedGet()')),
        ('Devices/Telemetry/SX1281/Src/sx1281_device.c','Devices/Telemetry/SX1281/Src/sx1281_device.c',NativeRadioDevice_Derive)):
        body=files[original]
        target_body=transform(body)
        archived=original if original!=derived else 'HardwareGenerated/ReviewedC071Radio/Original/'+original
        files[archived]=body;files[derived]=target_body
        patch=derived+'.patch'
        files[patch]=''.join(difflib.unified_diff(body.decode().splitlines(True),target_body.decode().splitlines(True),fromfile=original,tofile=derived)).encode()
        graph['sources']=[derived if p==original else p for p in graph['sources']]
        payload_derivatives.append({'original':archived,'derived':derived,'original_sha256':hashlib.sha256(body).hexdigest(),
            'derived_sha256':hashlib.sha256(target_body).hexdigest(),'patch':patch,'patch_sha256':hashlib.sha256(files[patch]).hexdigest()})
    files['Generated/Inc/c071_context.h']=b'#ifndef C071_CONTEXT_H\n#define C071_CONTEXT_H\n#include <stdint.h>\nuint8_t C071MainContext_AllowedGet(void);\n#endif\n'
    files['Generated/Src/c071_context.c']=b'#include "c071_context.h"\n#include "main.h"\nuint8_t C071MainContext_AllowedGet(void) { return ((__get_IPSR() == 0U) && (__get_PRIMASK() == 0U)) ? 1U : 0U; }\n'
    graph['sources'].append('Generated/Src/c071_context.c')
    from silverstar_fccg.generator.native_hal import _SpiBounded_Apply,_UartPointer_Apply
    hal_derivatives=[]
    for name,transform in (
        ('stm32c0xx_hal_spi.c',_SpiBounded_Apply),
        ('stm32c0xx_hal_uart.c',lambda text:_UartPointer_Apply(text,functions=(('HAL_UART_Transmit','gState'),))),
        ('stm32c0xx_hal_uart_ex.c',lambda text:_UartPointer_Apply(text,functions=(('HAL_UARTEx_ReceiveToIdle','RxState'),)))):
        relative='Drivers/STM32C0xx_HAL_Driver/Src/'+name
        original='HardwareGenerated/STM32CubeMX/'+relative
        derived='HardwareGenerated/ReviewedC071Hal/'+relative
        body=native[relative]
        if hashlib.sha256(body).hexdigest()!=profile['files_sha256'][relative]:
            raise ValueError('C071 exact native HAL profile changed')
        text=transform(body.decode('utf8'))
        files[derived]=text.encode()
        patch=derived+'.patch'
        files[patch]=''.join(difflib.unified_diff(body.decode().splitlines(True),text.splitlines(True),fromfile=original,tofile=derived)).encode()
        graph['sources']=[derived if p==original else p for p in graph['sources']]
        hal_derivatives.append({'original':original,'derived':derived,'original_sha256':hashlib.sha256(body).hexdigest(),
            'derived_sha256':hashlib.sha256(files[derived]).hexdigest(),'patch':patch,'patch_sha256':hashlib.sha256(files[patch]).hexdigest()})
    graph['native_hal_derivatives']=hal_derivatives
    graph['required_link_symbols']=['_sbrk']
    graph['formal_release']=False
    graph['independent_usb_review']='NO_PASSED_OUTCOME'
    records={'format_version':1,'scope':'PRIVATE_C071_GROUND_RUNTIME_CANDIDATE',
        'original_sha256':{p:hashlib.sha256(b).hexdigest() for p,b in native.items()},
        'payload_derivatives':payload_derivatives,'native_hal_derivatives':hal_derivatives,
        'ordinary_lifecycle_derivatives':lifecycle,
        'compiled_owned_sha256':{p:hashlib.sha256(files[p]).hexdigest() for p in graph['sources']},
        'input_kind':'native_pcd_plus_pinned_classic_cdc','native_cdc':False,
        'no_heap':'Rejecting _sbrk ABI; static class block; original sysmem retained, uncompiled',
        'independent_usb_review':'NO_PASSED_OUTCOME','formal_release':False,
        'limits':'EP0/async lifecycle, manual critical contracts, stack/WCET and hardware NOT PROVEN'}
    files['Generated/ground_source_graph.json']=json.dumps(graph,indent=2).encode()
    files['Generated/native_ground_contract.json']=json.dumps(records,indent=2).encode()
    # Export uses the final ownership graph too, including explicit ordinary
    # lifecycle/HAL derivatives and the rejecting heap owner.
    from types import SimpleNamespace
    from silverstar_fccg.generator.multi_target import _Makefile_Render
    make=_Makefile_Render(tuple(graph['sources']),tuple(graph['asm_sources']),tuple(graph['include_dirs']),
        tuple(graph['defines']),SimpleNamespace(**graph),model.ground_target.build.toolchain_prefix)
    make=make.replace('-Wl,--gc-sections,','-Wl,-u,_sbrk -Wl,--gc-sections,',1)
    for mode in ('architecture','host','artifact'):
        make=make.replace('$(PYTHON) Tools/check_ground.py '+mode,
            '$(PYTHON) Tools/check_c071_candidate.py'+('' if mode=='architecture' else ' '+mode))
    files['Makefile']=make.encode()
    return files,graph,records
