"""Isolated native Ground candidate. Normal generation remains blocked.

Silicon, clocks, startup, linker and native USB/HAL originals belong to the
import. This renderer adds SCG owners without selecting an MCU-family backend.
EP0 admission and complete critical-contract acceptance are separate pending
reviews; a successful private compilation must not claim runtime qualification.
"""
from __future__ import annotations

import hashlib
import json
import re
import difflib
from types import SimpleNamespace

from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet, NativeC_VisibleGet, NativeHalDerivatives_Render
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender, NativeClockSourceContract_Validate
from silverstar_fccg.generator.native_clock_tim import NativeClockTimSourceContract_Inspect,NativeClockTimDerivatives_Render,NativeClockTimPort_Render,NativeClockTimCallerDerivatives_Render
from silverstar_fccg.generator.native_usb_config import NativeUsbConfig_FilesRender
from silverstar_fccg.generator.native_platform import NativePlatformContract_Inspect, NativePlatform_FilesRender
from silverstar_fccg.generator.native_runtime import NativeRuntime_FilesRender
from silverstar_fccg.generator.native_no_heap import NativeNoHeap_FilesRender
from silverstar_fccg.generator.native_pc import NativePcAdapter_Render
from silverstar_fccg.generator.native_usb_data import NativeUsbBulk_FilesRender
from silverstar_fccg.generator.native_radio import NativeRadioHal_Derive, NativeRadioDevice_Derive
from silverstar_fccg.generator.ground_radio import GroundRadioConfig_Render, GroundRadioAirHeader_Render
from silverstar_fccg.generator.multi_target import _PayloadFiles_Add, _UserSection_Insert, _Makefile_Render
from silverstar_fccg.generator.render import AirLinkHeader_Render
from silverstar_fccg.project.model import GroundRadioConfigurations_Get


def _Function_Replace(source, name, replacement):
    start, _opening, end = NativeC_FunctionSpanGet(source, name)
    return source[:start] + replacement + source[end:]


def _Callback_Integrate(source: str, indexed: bool) -> str:
    visible = NativeC_VisibleGet(source)
    names = ['CDC_Init_FS','CDC_DeInit_FS','CDC_Control_FS','CDC_Receive_FS']
    if indexed:
        names.append('CDC_TransmitCplt_FS')
        _a,o,b=NativeC_FunctionSpanGet(source,'CDC_TransmitCplt_FS')
        if re.sub(r'\s+','',NativeC_VisibleGet(source[o+1:b-1]))!='uint8_tresult=USBD_OK;UNUSED(Buf);UNUSED(Len);UNUSED(epnum);returnresult;':
            raise ValueError('Native CDC completion hook requires its reviewed empty policy')
    initializer = re.findall(r'USBD_CDC_ItfTypeDef\s+USBD_Interface_fops_FS\s*=\s*\{([^{}]*)\}\s*;',visible)
    if (len(initializer) != 1 or re.fullmatch(r'\s*'+r'\s*,\s*'.join(names)+r'\s*,?\s*',initializer[0]) is None or
            re.search(r'(?m)^\s*#\s*(?:define|undef)\b',visible) or '\\\n' in source or '\\\r\n' in source):
        raise ValueError('Native CDC initializer needs exact literal callback owners without expressions/aliases')
    # Existing application data hooks must be stock empty CubeMX policy.
    for name, expected in (
            ('CDC_Init_FS','USBD_CDC_SetTxBuffer(&hUsbDeviceFS,UserTxBufferFS,0);USBD_CDC_SetRxBuffer(&hUsbDeviceFS,UserRxBufferFS);return(USBD_OK);'),
            ('CDC_DeInit_FS','return(USBD_OK);'),
            ('CDC_Receive_FS','USBD_CDC_SetRxBuffer(&hUsbDeviceFS,&Buf[0]);USBD_CDC_ReceivePacket(&hUsbDeviceFS);return(USBD_OK);')):
        _start, opening, end = NativeC_FunctionSpanGet(source, name)
        if re.sub(r'\s+','',NativeC_VisibleGet(source[opening+1:end-1])) != expected:
            raise ValueError('Native CDC refuses a nonempty/unreviewed data hook: '+name)
    source = source.replace('#include "usbd_cdc_if.h"','#include "usbd_cdc_if.h"\n#include "pc_byte_stream.h"',1)
    source = _Function_Replace(source,'CDC_Init_FS','''static int8_t CDC_Init_FS(void)
{
  PcByteStream_OnUsbReset();
  if ((USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U) != USBD_OK) ||
      (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS) != USBD_OK)) { return USBD_FAIL; }
  return USBD_OK;
}''')
    source = _Function_Replace(source,'CDC_DeInit_FS','''static int8_t CDC_DeInit_FS(void)
{ PcByteStream_OnUsbReset(); return USBD_OK; }''')
    source = _Function_Replace(source,'CDC_Receive_FS','''static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len)
{
  uint8_t result;
  if ((Buf == NULL) || (Len == NULL) || (*Len > 64U)) { return USBD_FAIL; }
  PcByteStream_OnUsbReceive(Buf, (uint16_t)*Len);
  result = USBD_CDC_SetRxBuffer(&hUsbDeviceFS, Buf);
  if (result == USBD_OK) { result = USBD_CDC_ReceivePacket(&hUsbDeviceFS); }
  if (result != USBD_OK) { PcByteStream_OnUsbReset(); }
  return (int8_t)result;
}''')
    # A checked setter must not be bypassed by the stock application wrapper.
    field = 'pClassDataCmsit[0]' if indexed else 'pClassData'
    source = _Function_Replace(source,'CDC_Transmit_FS','''uint8_t CDC_Transmit_FS(uint8_t *Buf, uint16_t Len)
{
  uint8_t result;
  if ((Buf == NULL) || (Len == 0U) || (Len > 70U) ||
      (hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
      (hUsbDeviceFS.'''+field+''' == NULL)) { return USBD_FAIL; }
  result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);
  if (result != USBD_OK) { return (result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL; }
  result = USBD_CDC_TransmitPacket(&hUsbDeviceFS);
  return (result == USBD_OK) ? USBD_OK : ((result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL);
}''')
    if indexed:
        source = _Function_Replace(source,'CDC_TransmitCplt_FS','''static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum)
{
  (void)Buf; (void)Len; (void)epnum;
  return (int8_t)USBD_OK;
}''')
        marker='  result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);'
        source=source.replace(marker,'  if ((hUsbDeviceFS.classId != 0U) ||\n'
            '      (hUsbDeviceFS.pClassData != hUsbDeviceFS.pClassDataCmsit[0]))\n'
            '  { NativeRuntime_TransportFaultRecord(); return USBD_FAIL; }\n'+marker,1)
        source=source.replace('#include "pc_byte_stream.h"','#include "pc_byte_stream.h"\n#include "native_runtime.h"',1)
    return source


def NativeGroundCandidate_Render(native_files, proof, inventory, model, catalog, *, hclk_hz):
    ground = model.ground_target
    radios = GroundRadioConfigurations_Get(ground)
    if (not ground.enabled or ground.pc_interface != 'usb_cdc' or len(radios) != 1 or
            radios[0].plugin != 'silverstar.device.telemetry.sx1281' or
            radios[0].module_variant != 'e28_2g4m12sx' or model.air_link.radio_family != 'sx128x' or
            ground.tx_led_resource or ground.rx_led_resource or ground.activity_led_enabled is True):
        raise ValueError('Private native candidate currently requires one bare SX1281/M12, FS CDC and no extra LEDs')
    class_sha=hashlib.sha256(native_files[proof['cdc']['owners']['usbd_cdc.c']]).hexdigest()
    indexed=class_sha=='794a6d0df08fc2b777678b99013f61d0a9c93f5fbeacfaa3466c0feeaa9ada39'
    clock = (NativeClockTimSourceContract_Inspect if indexed else NativeClockSourceContract_Validate)(
        native_files,proof['build']['sources'],hclk_hz=hclk_hz)
    platform = NativePlatformContract_Inspect(native_files,proof,inventory)
    files, replacements, hal = NativeHalDerivatives_Render(native_files,proof['build']['sources'])
    timer=None;usb_config=None;config_include=None
    if indexed:
        timer_files,timer_replacements,timer=NativeClockTimDerivatives_Render(native_files,runtime=True)
        files.update(timer_files);replacements.update(timer_replacements)
        caller_files,caller_replacements,callers=NativeClockTimCallerDerivatives_Render(native_files)
        files.update(caller_files);replacements.update(caller_replacements)
        timer['callers']=callers
        config_files,config_include,usb_config=NativeUsbConfig_FilesRender(native_files,proof['cdc']['owners'])
        files.update(config_files)
    bulk_files, bulk_replacements, bulk = NativeUsbBulk_FilesRender(native_files,proof['cdc']['owners'])
    files.update(bulk_files); replacements.update(bulk_replacements)
    core = catalog.Component_Get('silverstar.core.ground.0_1_0')
    radio = catalog.Component_Get(radios[0].plugin)
    _PayloadFiles_Add(files,core)
    # Native publication needs an unmasked clock probe; strengthen the final
    # legacy masked-write case to verify BUSY/no publication and mask retention.
    test_path = 'Tests/Host/usb_cdc.c'
    old = '    usb_test_mask = 1U;\n    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_OK);'
    text = files[test_path].decode().replace('\r\n','\n')
    if text.count(old) != 1:
        raise ValueError('Native Host masked-write contract owner changed')
    files[test_path] = text.replace(old, '    calls = s_calls;\n    usb_test_mask = 1U;\n'
        '    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);\n'
        '    assert(s_calls == calls);', 1).encode()
    if indexed:
        header_path='Tests/Host/usb_device.h'
        header=files[header_path].decode().replace('void *pClassData;',
            'void *pClassData; void *pClassDataCmsit[1]; uint8_t classId;')
        files[header_path]=header.encode()
        # Model the actual single-class ABI in every already-ready Host case,
        # including reset/reconnect transitions; retain all test expectations.
        for name,count in (('usb_cdc.c',3),('usb_session.c',1),('ground_backpressure.c',1)):
            path='Tests/Host/'+name
            text,actual=re.subn(r'hUsbDeviceFS\.pClassData\s*=\s*([^;]+);',
                lambda match:match[0]+' hUsbDeviceFS.pClassDataCmsit[0] = '+match[1]+';',files[path].decode())
            if actual!=count:raise ValueError('Native indexed Host ABI fixture changed: '+name)
            files[path]=text.encode()
    files.pop(core.metadata['ground_radio_backends']['nrf24'])
    _PayloadFiles_Add(files,radio,skip_adapter=True)
    radio_original='Middlewares/Third_Party/SX1280lib/sx1280-hal.c'
    radio_derived='Middlewares/ReviewedNativeRadio/SX1280lib/sx1280-hal.c'
    original_radio=files[radio_original]
    files[radio_derived]=NativeRadioHal_Derive(original_radio)
    files[radio_derived+'.patch']=''.join(difflib.unified_diff(original_radio.decode().splitlines(keepends=True),
        files[radio_derived].decode().splitlines(keepends=True),fromfile=radio_original,tofile=radio_original)).encode()
    device_path='Devices/Telemetry/SX1281/Src/sx1281_device.c'
    device_archive='Evidence/NativePayloads/'+device_path+'.original'
    original_device=files[device_path]
    files[device_archive]=original_device
    files[device_path]=NativeRadioDevice_Derive(original_device)
    files[device_archive+'.patch']=''.join(difflib.unified_diff(original_device.decode().splitlines(keepends=True),
        files[device_path].decode().splitlines(keepends=True),fromfile=device_path,tofile=device_path)).encode()
    api = catalog.Component_Get('silverstar.platform.api')
    _PayloadFiles_Add(files,api)
    flight_core = catalog.Component_Get(model.core)
    for path in ('Common/Inc/silverstar_assert.h','Common/Inc/silverstar_compiler.h','Common/Src/silverstar_assert.c',
                 'Interfaces/Inc/system_device_types.h','Tools/check_power_of_ten.ps1'):
        files[path] = (flight_core.payload_root/path).read_bytes()
    files.update(NativeClock_FilesRender(hclk_hz=hclk_hz))
    if indexed:files['Generated/Src/native_clock_port.c']=NativeClockTimPort_Render()
    files.update(NativePlatform_FilesRender(platform))
    files.update(NativeRuntime_FilesRender(transport_fault=indexed))
    heap_owners = [path for path in proof['build']['sources'] if path.endswith('/sysmem.c')]
    if len(heap_owners) != 1:
        raise ValueError('Native candidate requires one known libc heap extender to replace')
    files.update(NativeNoHeap_FilesRender(native_files[heap_owners[0]]))
    replacements[NATIVE_PREFIX+heap_owners[0]] = 'Generated/Src/native_no_heap.c'
    files['Generated/Inc/native_usb_state.h'] = b'''#ifndef __NATIVE_USB_STATE_H
#define __NATIVE_USB_STATE_H
typedef enum { NativeUsbResult_Ok, NativeUsbResult_Failure } NativeUsbResult;
NativeUsbResult NativeUsb_Stop(void);
#endif /* __NATIVE_USB_STATE_H */
'''
    files['Generated/Src/native_usb_state.c'] = b'''#include "native_usb_state.h"
#include "usb_device.h"
#include "usbd_core.h"

extern USBD_HandleTypeDef hUsbDeviceFS;
NativeUsbResult NativeUsb_Stop(void)
{
    USBD_StatusTypeDef result = USBD_LL_Stop(&hUsbDeviceFS);
    /* Gate publication even if the lower controller cannot confirm stopping.
     * The runtime records retirement failure and enters its terminal path. */
    hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT;
    return (result == USBD_OK) ? NativeUsbResult_Ok : NativeUsbResult_Failure;
}
'''
    files['Generated/Inc/project_resources.h'] = b'''#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_SX1281_INSTANCE_COUNT 1U
#define PROJECT_SX1281_INSTANCE_COUNT_MAX 4U
typedef struct {
    PlatformSpiId spi; PlatformGpioId nss,reset,busy,dio1;
    PlatformTimeId time; PlatformGpioId rx_en,tx_en;
} ProjectSx1281Resources;
SystemDeviceResult ProjectSx1281Resources_Get(uint8_t instance,ProjectSx1281Resources *resources);
#endif /* __PROJECT_RESOURCES_H */
'''
    files['Generated/Src/project_resources.c'] = b'''#include "project_resources.h"
#include <stddef.h>
SystemDeviceResult ProjectSx1281Resources_Get(uint8_t instance,ProjectSx1281Resources *resources)
{
    if (resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance >= PROJECT_SX1281_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *resources = (ProjectSx1281Resources){PLATFORM_SPI_1,PLATFORM_GPIO_0,PLATFORM_GPIO_1,
        PLATFORM_GPIO_2,PLATFORM_GPIO_3,PLATFORM_TIME_1,
        (PlatformGpioId)PLATFORM_GPIO_COUNT,(PlatformGpioId)PLATFORM_GPIO_COUNT};
    return SYSTEM_DEVICE_OK;
}
'''
    files['Generated/Inc/ground_radio_config.h'] = GroundRadioConfig_Render(ground).encode()
    files['Generated/Inc/air_link_config.h'] = GroundRadioAirHeader_Render(ground,AirLinkHeader_Render(model,target='ground')).encode()
    usb_class_digest = hashlib.sha256(native_files[proof['cdc']['owners']['usbd_cdc.c']]).hexdigest()
    usb_profiles = {
        '9bf6b6c49a7faab7bdc465dae5df52bcc878720bd354c8596b51e16d6e210ecb':False,
        '794a6d0df08fc2b777678b99013f61d0a9c93f5fbeacfaa3466c0feeaa9ada39':True}
    if usb_class_digest not in usb_profiles:
        raise ValueError('Native USB data ABI needs a reviewed class source profile')
    indexed = usb_profiles[usb_class_digest]
    files['Generated/Src/pc_byte_stream.c'] = NativePcAdapter_Render(indexed=indexed).encode()
    files['Tools/native_machine_contract.py'] = (core.payload_root.parents[3]/
        'src/silverstar_fccg/hardware/native_machine_contract.py').read_bytes()
    main_path = proof['cdc']['owners']['main.c']
    main = native_files[main_path].decode('utf-8-sig')
    _start, opening, end = NativeC_FunctionSpanGet(main, 'main')
    boot = NativeC_VisibleGet(main[opening+1:end-1])
    owner_start = main.index('/* USER CODE BEGIN 2 */') - opening - 1
    gpio_calls = list(re.finditer(r'\bMX_GPIO_Init\s*\(\s*\)\s*;', boot))
    spi_calls = list(re.finditer(r'\bMX_SPI1_Init\s*\(\s*\)\s*;', boot))
    if (len(gpio_calls) != 1 or len(spi_calls) != 1 or
            not (gpio_calls[0].start() < spi_calls[0].start() < owner_start)):
        raise ValueError('Native lifecycle requires GPIO and SPI initialization before its owner boundary')
    if indexed:
        if hashlib.sha256(native_files[main_path]).hexdigest()!='b29d5f13e084cf835c1845095dc19243f00411d3c6198ca25b3477993923aca8':
            raise ValueError('Native TIM1 Ground boot/configuration sequence requires reviewed main profile')
        if not (boot.index('HAL_Init();') < boot.index('SystemClock_Config();') < gpio_calls[0].start()):
            raise ValueError('Native TIM1 Ground requires both stock boot clock phases before owner initialization')
    main = _UserSection_Insert(main,'Includes','#include "native_runtime.h"',empty=True)
    main = _UserSection_Insert(main,'2','  if (NativeRuntime_Init() != NativeRuntimeResult_Ok) { Error_Handler(); }',empty=True)
    loop = re.findall(r'/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/',main,re.S)
    if len(loop) != 1 or loop[0].strip() != '}' or main.count('HAL_Init();') != 1:
        raise ValueError('Native main requires empty stock owner loop and one HAL initialization')
    main = main.replace('HAL_Init();','if (HAL_Init() != HAL_OK) { Error_Handler(); }',1)
    main = main.replace('/* USER CODE BEGIN 3 */','''/* USER CODE BEGIN 3 */
    NativeRuntimeResult result = NativeRuntime_Process();
    if ((result != NativeRuntimeResult_Ok) && (result != NativeRuntimeResult_RadioFailure) &&
        (result != NativeRuntimeResult_PcFailure)) { Error_Handler(); }
    /* Ordinary PC/radio failure diagnostics remain owned by Ground; retry in
     * the next bounded owner iteration. Clock/platform faults stop this loop. */''',1)
    main_owned = 'HardwareGenerated/ReviewedNativeEntry/'+main_path
    files[main_owned] = main.encode()
    replacements[NATIVE_PREFIX+main_path] = main_owned
    callback = proof['cdc']['owners']['usbd_cdc_if.c']
    header = native_files[callback.removesuffix('.c')+'.h'].decode('utf-8-sig')
    for name, minimum in (('APP_RX_DATA_SIZE',64),('APP_TX_DATA_SIZE',70)):
        sizes = re.findall(r'(?m)^\s*#define\s+'+name+r'\s+(\d+)\s*$',header)
        if len(sizes) != 1 or not minimum <= int(sizes[0]) <= 65535:
            raise ValueError('Native CDC static application buffer capacity is unproved: '+name)
    callback_owned = 'HardwareGenerated/ReviewedNativeData/'+callback
    files[callback_owned] = _Callback_Integrate(native_files[callback].decode('utf-8-sig'),indexed).encode()
    replacements[NATIVE_PREFIX+callback] = callback_owned
    sources = [replacements.get(NATIVE_PREFIX+p,NATIVE_PREFIX+p) for p in proof['build']['sources']]
    sources.extend(p for p in files if p.endswith('.c') and p.startswith(('Generated/','Common/')) and p not in sources)
    for owner in (core,radio):
        sources.extend(p for p in owner.build.sources if '/Adapter/' not in p and p in files)
    sources=[radio_derived if path==radio_original else path for path in sources]
    includes = [NATIVE_PREFIX+p for p in proof['build']['include_dirs']]
    if config_include:includes.insert(0,config_include)
    includes.extend(['Generated/Inc','Common/Inc','Interfaces/Inc','Platform/Inc'])
    includes.extend(p for owner in (core,radio) for p in owner.build.include_dirs if '/Adapter/' not in p)
    graph = {**proof['build'],'sources':list(dict.fromkeys(sources)),
        'asm_sources':[NATIVE_PREFIX+p for p in proof['build']['asm_sources']],
        'include_dirs':list(dict.fromkeys(includes)),
        'defines':list(dict.fromkeys([*proof['build']['defines'],'SILVERSTAR_AIR_LINK_ENABLED=1','AIR_LINK_HAL_BUFFER_SIZE=260'])),
        'linker_script':NATIVE_PREFIX+proof['build']['linker_script'],
        'required_irq_handlers':proof['required_irq_handlers'], 'required_link_symbols':['_sbrk'],
        'native_complete_classic_cdc':True}
    absent = [path for path in (*graph['sources'],*graph['asm_sources']) if path not in files and path.removeprefix(NATIVE_PREFIX) not in native_files]
    if absent:
        raise ValueError('Native candidate source graph is not closed: '+', '.join(absent))
    records = {'format_version':1,'clock':clock,'platform':platform,'hal':hal,'usb_bulk':bulk,'source_replacements':replacements,
        'payload_derivatives':[{'original':radio_original,'derived':radio_derived,
            'original_sha256':hashlib.sha256(original_radio).hexdigest(),
            'derived_sha256':hashlib.sha256(files[radio_derived]).hexdigest(),
            'patch':radio_derived+'.patch','patch_sha256':hashlib.sha256(files[radio_derived+'.patch']).hexdigest(),
            'contract':'Main-only one radio/SPI owner; DIO ISR records flag only; tick/USB IRQs remain enabled; MCU Wakeup timing NOT PROVEN'},
            {'original':device_archive,'logical_payload':device_path,'derived':device_path,
            'original_sha256':hashlib.sha256(original_device).hexdigest(),
            'derived_sha256':hashlib.sha256(files[device_path]).hexdigest(),
            'patch':device_archive+'.patch','patch_sha256':hashlib.sha256(files[device_archive+'.patch']).hexdigest(),
            'contract':'Main-owned timestamps sampled immediately before existing IRQ locks; state/queue guards retained; actual generated first-party driver remains in Devices and Power10 scope'}],
        'compiled_owned_sha256':{path:hashlib.sha256(files[path]).hexdigest() for path in graph['sources'] if path in files},
        'original_sha256':{path:hashlib.sha256(content).hexdigest() for path,content in native_files.items()},
        'ep0_review':'NOT PROVEN: shared owner patch independent review blocked; no EP0 repair integrated',
        'critical_contract_review':'NOT PROVEN: private bulk propagation increment requires manual acceptance; complete EP0/async lifecycle, call graph, stack/WCET/hardware unavailable',
        'publication':'PRIVATE CANDIDATE ONLY; normal generation remains blocked'}
    if indexed:
        records.update(timer=timer,usb_config=usb_config,required_symbol_owners={
            'HAL_InitTick':replacements[NATIVE_PREFIX+'Core/Src/stm32f4xx_hal_timebase_tim.c'],
            'TIM1_UP_TIM10_IRQHandler':replacements[NATIVE_PREFIX+'Core/Src/stm32f4xx_it.c'],
            'HAL_TIM_PeriodElapsedCallback':main_owned})
        records['timer_lifecycle']='Only stock HAL_Init then SystemClock_Config boot phases before PlatformTime_Init; later/masked/ISR InitTick rejected and latched, sole timer IRQ quiesced before boot reconfiguration'
    files['Generated/native_ground_contract.json'] = json.dumps(records,indent=2).encode()
    files['Generated/ground_source_graph.json'] = json.dumps(graph,indent=2).encode()
    make = _Makefile_Render(tuple(graph['sources']),tuple(graph['asm_sources']),tuple(graph['include_dirs']),
        tuple(graph['defines']),SimpleNamespace(**graph),ground.build.toolchain_prefix)
    make = make.replace('-Wl,--gc-sections,','-Wl,-u,_sbrk -Wl,--gc-sections,',1)
    make = make.replace('$(PYTHON) Tools/check_ground.py architecture','$(PYTHON) Tools/check_native_ground.py')
    make = make.replace('$(PYTHON) Tools/check_ground.py host','$(PYTHON) Tools/check_native_ground.py host')
    make = make.replace('$(PYTHON) Tools/check_ground.py artifact','$(PYTHON) Tools/check_native_ground.py artifact')
    files['Makefile'] = make.encode()
    return files,graph,records
