"""Actual C071 standalone artifacts; explicitly separate from CubeMX gates."""
from pathlib import Path
import argparse, hashlib, json, re, struct, subprocess, sys
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('target',type=Path)
parser.add_argument('--prefix',default='arm-none-eabi-')
args = parser.parse_args()
root = args.target.resolve(); prefix = args.prefix
sys.path.insert(0,str(root/'Tools'))
from check_ground import Architecture_Check
from ground_artifact_contract import InterruptVectors_Validate, DependencyClosure_Validate
graph = Architecture_Check(root)
if graph.get('complete_cube_import') or graph.get('experimental_standalone_mcu')!='STM32C071FBP6':
    raise ValueError('this gate requires the explicit standalone FBP6 candidate')
manifest = json.loads((root/'candidate-manifest.json').read_text(encoding='utf-8'))
actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() and path.relative_to(root).parts[0]!='build' and path.name!='candidate-manifest.json'}
if actual != set(manifest['files_sha256']): raise ValueError('candidate input file set changed')
for path,digest in manifest['files_sha256'].items():
    if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest: raise ValueError('candidate file changed: '+path)
def command(suffix,*values):
    return subprocess.check_output([prefix+suffix,*map(str,values)],cwd=root,text=True)
elf = root/'build/ground.elf'
attributes = command('readelf','-A',elf)
print(attributes)
if 'Tag_CPU_arch: v6S-M' not in attributes or 'Thumb-1' not in attributes or 'VFP registers' in attributes:
    raise ValueError('linked ABI is not ARMv6-M soft float')
symbols = command('nm','-g',elf)
mode=graph.get('pc_interface','usb_cdc')
required=['main','GroundBridge_Init','GroundBridge_Process','PcByteStream_WriteSession','PcByteStream_ReadSession','MX_SPI1_Init','SilverStarAssert_Fail']
required += ['USBD_CDC_TransmitPacket','HAL_PCD_IRQHandler','MX_USB_Device_Init'] if mode=='usb_cdc' else ['PcByteStream_Service','HAL_UART_IRQHandler','MX_USART2_UART_Init','HAL_UART_Receive_IT','HAL_UART_Transmit_IT','HAL_UART_RxCpltCallback','HAL_UART_ErrorCallback']
for name in required:
    if not re.search(r'(?m)^[0-9a-f]+ T '+name+r'$',symbols): raise ValueError('required real implementation missing: '+name)
for name in (('MX_USART2_UART_Init','HAL_UART_Receive_IT','HAL_UART_Transmit_IT') if mode=='usb_cdc' else ('MX_USB_Device_Init','USBD_CDC_TransmitPacket','MX_USB_PCD_Init')):
    if re.search(r'(?m)^[0-9a-f]+ [TW] '+name+r'$',symbols): raise ValueError('disabled PC transport remains linked: '+name)
if re.search(r'(?m)^[0-9a-f]+ [TW] (_?malloc\w*|_?sbrk\w*|_?printf\w*|_write|_read)$',symbols):
    raise ValueError('unexpected dynamic allocation/stdio implementation linked')
vector = root/'build/c071-vector.bin'
subprocess.run([prefix+'objcopy','-j','.isr_vector','-O','binary',str(elf),str(vector)],check=True)
InterruptVectors_Validate(root,graph,symbols,vector.read_bytes())
if struct.unpack_from('<I',vector.read_bytes())[0] != 0x20006000:
    raise ValueError('initial FBP6 stack pointer is not the end of its 24KB SRAM')
DependencyClosure_Validate(root,graph,prefix+'gcc')
flags = [*graph['mcu_flags'],*['-I'+path for path in graph['include_dirs']],*['-D'+value for value in graph['defines']]]
macros = {}
for source in (next(path for path in graph['sources'] if path.endswith('/main.c')),next(path for path in graph['sources'] if path.endswith('/stm32c0xx_hal_rcc.c'))):
    dump = command('gcc','-E','-dM',*flags,source)
    selected = re.findall(r'(?m)^#define (STM32C[0-9]{3}[A-Za-z0-9]+)\s+([^\r\n]*)$',dump)
    if selected != [('STM32C071xx','1')]: raise ValueError('effective C071 device macro changed')
    for name in ('HSI_VALUE','HSI48_VALUE'):
        value = re.search(r'(?m)^#define '+name+r'\s+\(?48000000[Uu][Ll]?\)?\s*$',dump)
        if value is None: raise ValueError('effective native 48MHz clock macro changed: '+name)
    macros[source] = {'STM32C071xx':1,'HSI_VALUE':48000000,'HSI48_VALUE':48000000}
    print('PASS actual C071/48MHz preprocessing',source)
power = {'supply':'not a USB PC transport','budget_status':'NOT PROVEN: final BOM and measured current'}
if mode=='usb_cdc':
    cdc_source=next(path for path in graph['sources'] if path.endswith('/usbd_cdc.c'))
    dump=command('gcc','-E','-dM',*flags,cdc_source)
    if not re.search(r'(?m)^#define USBD_SELF_POWERED\s+0U\s*$',dump):
        raise ValueError('mini must not advertise self-powered USB')
    if not re.search(r'(?m)^#define USBD_MAX_POWER\s+0x32U\s*$',dump):
        raise ValueError('reviewed USB current declaration changed')
    all_symbols=command('nm','-S','--defined-only',elf)
    desc=re.search(r'(?m)^([0-9a-f]+) ([0-9a-f]+) [dD] USBD_CDC_CfgDesc$',all_symbols)
    sections=command('objdump','-h',elf)
    data_section=re.search(r'(?m)^\s*\d+\s+\.data\s+([0-9a-f]+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)',sections)
    if desc is None or data_section is None: raise ValueError('linked CDC configuration descriptor missing')
    address,length=map(lambda value:int(value,16),desc.groups())
    size,vma,offset=map(lambda value:int(value,16),data_section.groups())
    if address<vma or address+length>vma+size: raise ValueError('CDC descriptor outside linked data')
    header=elf.read_bytes()[offset+address-vma:offset+address-vma+9]
    if len(header)!=9 or header[0:2]!=bytes((9,2)) or header[7:]!=bytes((0x80,0x32)):
        raise ValueError('actual USB descriptor is not bus-powered, 100 mA')
    power={'supply':'bus-powered VBUS to 3.3V','self_powered':False,'declared_max_ma':100,
           'linked_configuration_header_hex':header.hex(),
           'budget_status':'NOT PROVEN: module maximum, final BOM, inrush and suspend current'}
    print('PASS actual linked USB descriptor: bus-powered, bMaxPower=0x32 (100 mA)',header.hex())
size = command('size',elf)
text,data,bss = map(int,size.splitlines()[1].split()[:3])
linker = (root/graph['linker_script']).read_text(encoding='utf-8')
if not all(token in linker for token in ('LENGTH = 24K','LENGTH = 128K','_Min_Heap_Size = 0x0','_Min_Stack_Size = 0x800')):
    raise ValueError('FBP6 memory/reservation contract changed')
if text+data>131072 or data+bss>24576: raise ValueError('actual image exceeds FBP6 memory')
main = (root/next(path for path in graph['sources'] if path.endswith('/main.c'))).read_text(encoding='utf-8')
config = (root/(next(path for path in graph['sources'] if path.endswith('/usbd_conf.c')) if mode=='usb_cdc' else 'NativeCubeMX/Core/Src/usb.c')).read_text(encoding='utf-8')
for token in ('RCC_HSI48_ON','RCC_CRS_SYNC_SOURCE_USB','RCC_SYSCLKSOURCE_HSI','RCC_SYSCLK_DIV1','RCC_HSI_DIV1'):
    if token not in main: raise ValueError('native clock/CRS source contract missing: '+token)
if 'RCC_USBCLKSOURCE_HSI48' not in config: raise ValueError('USB clock selection missing')
native = root/'NativeCubeMX'
for relative,tokens in {
    'Core/Src/gpio.c':('HAL_GPIO_WritePin(GPIOA, RADIO_RESET_Pin|RADIO_NSS_Pin, GPIO_PIN_SET)','GPIO_MODE_IT_RISING','HAL_NVIC_EnableIRQ(EXTI2_3_IRQn)'),
    'Core/Inc/main.h':('#define RADIO_DIO1_Pin GPIO_PIN_3','#define RADIO_DIO1_GPIO_Port GPIOB'),
    'Core/Src/spi.c':('SPI_BAUDRATEPRESCALER_16','SPI_POLARITY_LOW','SPI_PHASE_1EDGE','SPI_NSS_PULSE_DISABLE','SPI_NSS_SOFT'),
    'Core/Src/usart.c':('huart2.Init.BaudRate = 230400','UART_WORDLENGTH_8B','UART_STOPBITS_1','UART_PARITY_NONE'),
    'Core/Src/stm32c0xx_it.c':('HAL_GPIO_EXTI_IRQHandler(RADIO_DIO1_Pin)','HAL_UART_IRQHandler(&huart2)'),
}.items():
    body=(native/relative).read_text(encoding='utf-8')
    if not all(token in body for token in tokens): raise ValueError('native SPI/UART/PB3 contract changed: '+relative)
resources=(root/'Generated/Src/platform_resources.c').read_text(encoding='utf-8')
if '{GPIOB,GPIO_PIN_3,1U}' not in resources: raise ValueError('radio resource no longer uses native PB3 DIO1')
pma = [(int(address,16),8 if endpoint=='CDC_CMD_EP' else 64) for endpoint,address in re.findall(r'HAL_PCDEx_PMAConfig\([^,]+,\s*(\w+|0x\w+)\s*,\s*PCD_SNG_BUF,\s*(0x\w+)\)',config)]
if mode=='usb_cdc' and (len(pma)!=5 or any(address+length>2048 for address,length in pma)): raise ValueError('C071 2KB PMA profile changed')
for left,right in zip(sorted(pma),sorted(pma)[1:]):
    if left[0]+left[1]>right[0]: raise ValueError('overlapping PMA buffers')
frames = {}
for path in (root/'build').rglob('*.su'):
    if 'analysis' in path.parts: continue
    for line in path.read_text(encoding='utf-8').splitlines():
        name,usage,kind = line.split('\t'); frames[name.rsplit(':',1)[-1]]={'bytes':int(usage),'kind':kind}
result = {'mcu':'STM32C071FBP6','pc_interface':mode,'input_kind':'native CubeMX v2 with explicitly selected PC transport','actual_abi':attributes,'sources':len(graph['sources']),'text':text,'data':data,'bss_including_reserved_stack':bss,'flash_used':text+data,'ram_unallocated':24576-data-bss,'stack_reserved':2048,'heap_reserved':0,'effective_macros':macros,'usb_power_profile':power,'pma_regions':pma,'frames':frames,'artifacts_sha256':{path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in (elf,root/'build/ground.bin',root/'build/ground.map',root/'Generated/ground_source_graph.json',root/'candidate-manifest.json')},'remaining':'NOT PROVEN: complete critical contracts, C0 callback/board review, whole-program stack/WCET, hardware USB/UART/radio; no full SCG C0/USBX support; permanent main scheduler requires exact authorization'}
(root/'build/c071-evidence.json').write_text(json.dumps(result,indent=2))
print('PASS actual C071 ARM link/vector/dependencies/clock/PMA/memory',text,data,bss,'unallocatedRAM',result['ram_unallocated'])
print(result['remaining'])
