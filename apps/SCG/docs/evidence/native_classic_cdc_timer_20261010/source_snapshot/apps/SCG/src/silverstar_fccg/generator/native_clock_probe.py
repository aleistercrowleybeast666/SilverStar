"""Owned private TIM1 compile probe; this deliberately is not Ground runtime."""
import hashlib,json,difflib,re
from types import SimpleNamespace
from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender
from silverstar_fccg.generator.native_clock_tim import NativeClockTimSourceContract_Inspect, NativeClockTimDerivatives_Render, NativeClockTimPort_Render
from silverstar_fccg.generator.native_usb_config import NativeUsbConfig_FilesRender
from silverstar_fccg.generator.native_hal import NativeHalDerivatives_Render
from silverstar_fccg.generator.native_no_heap import NativeNoHeap_FilesRender
from silverstar_fccg.generator.multi_target import _UserSection_Insert, _Makefile_Render


def NativeTimerProbe_FilesRender(native_files,proof,*,hclk_hz,scg_root):
    clock=NativeClockTimSourceContract_Inspect(native_files,proof['build']['sources'],hclk_hz=hclk_hz)
    files,replacements,hal=NativeHalDerivatives_Render(native_files,proof['build']['sources'])
    timer,timer_replacements,timer_manifest=NativeClockTimDerivatives_Render(native_files)
    files.update(timer);replacements.update(timer_replacements)
    config,config_include,config_manifest=NativeUsbConfig_FilesRender(native_files,proof['cdc']['owners'])
    files.update(config)
    files.update(NativeClock_FilesRender(hclk_hz=hclk_hz))
    files['Generated/Src/native_clock_port.c']=NativeClockTimPort_Render()
    api=scg_root/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    for path in api.glob('*.h'):files['Platform/Inc/'+path.name]=path.read_bytes()
    core=scg_root/'plugins/builtin/silverstar_core_0_1_0/payload'
    for path in ('Common/Inc/silverstar_assert.h','Common/Inc/silverstar_compiler.h',
        'Common/Src/silverstar_assert.c','Tools/check_power_of_ten.ps1'):
        files[path]=(core/path).read_bytes()
    heaps=[p for p in proof['build']['sources'] if p.endswith('/sysmem.c')]
    if len(heaps)!=1:raise ValueError('Native timer probe requires one reviewed heap extender')
    files.update(NativeNoHeap_FilesRender(native_files[heaps[0]]))
    replacements[NATIVE_PREFIX+heaps[0]]='Generated/Src/native_no_heap.c'
    main_path=proof['cdc']['owners']['main.c'];main=native_files[main_path].decode('utf-8-sig')
    main=_UserSection_Insert(main,'Includes','#include "native_clock.h"\n#include "platform_time.h"',empty=True)
    main=_UserSection_Insert(main,'2','  if (PlatformTime_Init() != PLATFORM_OK) { Error_Handler(); }',empty=True)
    loop=re.findall(r'/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/',main,re.S)
    if len(loop)!=1 or loop[0].strip()!='}' or main.count('HAL_Init();')!=1:
        raise ValueError('Native timer probe refuses an existing owner loop')
    main=main.replace('HAL_Init();','if (HAL_Init() != HAL_OK) { Error_Handler(); }',1)
    main=main.replace('/* USER CODE BEGIN 3 */','''/* USER CODE BEGIN 3 */
    uint64_t now_us;
    if (NativeClock_Read(&now_us) != NativeClockResult_Ok) { Error_Handler(); }''',1)
    main_owned='HardwareGenerated/ReviewedNativeEntry/'+main_path;files[main_owned]=main.encode()
    replacements[NATIVE_PREFIX+main_path]=main_owned
    linker_path=proof['build']['linker_script'];linker=native_files[linker_path].decode('utf-8-sig')
    heap=re.findall(r'(?m)^_Min_Heap_Size\s*=\s*(0x[\da-fA-F]+)\s*;',linker)
    if len(heap)!=1 or int(heap[0],16) not in (0,512):
        raise ValueError('Native timer linker heap reservation requires review')
    derived_linker=re.sub(r'(?m)^_Min_Heap_Size\s*=\s*0x[\da-fA-F]+\s*;',
        '_Min_Heap_Size = 0x0;',linker)
    owned_linker='HardwareGenerated/ReviewedNativeLinker/'+linker_path;files[owned_linker]=derived_linker.encode()
    linker_patch=owned_linker+'.patch'
    files[linker_patch]=''.join(difflib.unified_diff(linker.splitlines(keepends=True),derived_linker.splitlines(keepends=True),
        fromfile=NATIVE_PREFIX+linker_path,tofile=NATIVE_PREFIX+linker_path)).encode()
    graph={**proof['build'],'sources':[replacements.get(NATIVE_PREFIX+p,NATIVE_PREFIX+p) for p in proof['build']['sources']],
        'asm_sources':[NATIVE_PREFIX+p for p in proof['build']['asm_sources']],
        'include_dirs':[config_include,*[NATIVE_PREFIX+p for p in proof['build']['include_dirs']],
            'Generated/Inc','Platform/Inc','Common/Inc'],
        'linker_script':owned_linker,'required_irq_handlers':proof['required_irq_handlers'],
        'required_link_symbols':['_sbrk'],'native_timer_probe':True}
    # The rejecting heap owner already replaces native sysmem in the graph.
    # Append only additional owned sources; do not give that same file two
    # compilation owners or hide collisions between distinct object paths.
    graph['sources'] += [p for p in files if p.startswith(('Common/','Generated/'))
        and p.endswith('.c') and p not in graph['sources']]
    for name in ('native_machine_contract.py',):
        files['Tools/'+name]=(scg_root/'src/silverstar_fccg/hardware'/name).read_bytes()
    tools=scg_root/'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools'
    for name in ('check_native_ground.py','check_native_probe.py','ground_artifact_contract.py'):
        files['Tools/'+name]=(tools/name).read_bytes()
    records={'source_replacements':replacements,'original_sha256':{p:hashlib.sha256(v).hexdigest() for p,v in native_files.items()},
        'compiled_owned_sha256':{p:hashlib.sha256(files[p]).hexdigest() for p in graph['sources'] if p in files},
        'clock':clock,'timer':timer_manifest,'hal':hal,'usb_config':config_manifest,
        'linker':{'original':NATIVE_PREFIX+linker_path,'derived':owned_linker,'patch':linker_patch,
            'original_sha256':hashlib.sha256(native_files[linker_path]).hexdigest(),'derived_sha256':hashlib.sha256(files[owned_linker]).hexdigest()},
        'required_symbol_owners':{'HAL_InitTick':replacements[NATIVE_PREFIX+'Core/Src/stm32f4xx_hal_timebase_tim.c'],
            'TIM1_UP_TIM10_IRQHandler':replacements[NATIVE_PREFIX+'Core/Src/stm32f4xx_it.c'],
            'HAL_TIM_PeriodElapsedCallback':main_owned},
        'scope':'Private actual TIM1 clock/HAL/config compilation probe, NOT Ground runtime or EP0 acceptance',
        'critical_contract_review':'NOT PROVEN','runtime_generation':'BLOCKED'}
    files['Generated/native_probe_contract.json']=json.dumps(records,indent=2).encode()
    return files,graph,records


def NativeTimerProbe_MakeRender(graph,prefix):
    make=_Makefile_Render(tuple(graph['sources']),tuple(graph['asm_sources']),tuple(graph['include_dirs']),
        tuple(graph['defines']),SimpleNamespace(**graph),prefix)
    make=make.replace('-Wl,--gc-sections,','-Wl,-u,_sbrk -Wl,--gc-sections,',1)
    make=make.replace('$(PYTHON) Tools/check_ground.py architecture','$(PYTHON) Tools/check_native_probe.py architecture')
    make=make.replace('$(PYTHON) Tools/check_ground.py host','$(PYTHON) Tools/check_native_probe.py host')
    make=make.replace('$(PYTHON) Tools/check_ground.py artifact','$(PYTHON) Tools/check_native_probe.py artifact')
    # A probe has no Ground host program. Its actual owner/port fault cases are
    # run by pytest; the target explicitly refuses a fabricated host pass.
    return make
