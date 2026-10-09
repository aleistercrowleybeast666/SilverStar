"""Experimental C071FBP6 classic CDC software recipe, not a CubeMX importer.

Requires pinned official sources fetched by c071_fetch.py. Writes only a new
empty output directory. No hardware or upload command is provided.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse, hashlib, json, re, sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--official', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cubemx', type=Path, required=True, help='Complete native CubeMX C071FBP6 PCD project')
args = parser.parse_args()
SCG = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(SCG/'src'),str(SCG/'tests')]
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.generator.multi_target import GroundFiles_Render, _Makefile_Render, _UsbConf_Integrate
from silverstar_fccg.generator.ground_pc_usb_cdc import PcUsbCdc_Render
from test_round2_targets import _GroundBoardProject_Get

official, output = args.official.resolve(), args.output.resolve()
if official == output or official.is_relative_to(output) or output.is_relative_to(official):
    raise ValueError('input and new output must be disjoint')
if output.exists() and any(output.iterdir()): raise ValueError('output must be empty')
manifest = json.loads((official/'source-manifest.json').read_text(encoding='utf-8'))
if [item['commit'] for item in manifest['sources']] != ['334655ed5eb719db18fa5990a5044332eeca59dc','311fc3cfd91898974a583ce15261fd7aacb8cf2f','a8515e2d45fa28201fe769b3b27fe1bbdf237c50','947131e000d1ecebc260f22010fa75486c50b423']:
    raise ValueError('unreviewed official source revision')
for item in manifest['files']:
    path = (official/item['path']).resolve()
    if not path.is_relative_to(official) or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError('official snapshot changed: '+item['path'])

catalog = PluginCatalog(SCG/'plugins/builtin',SCG/'plugins/installed'); catalog.Scan()
model = _GroundBoardProject_Get(catalog)
base = GroundFiles_Render(model,catalog,WorkspacePolicy(SCG))
files = {}
def port(value):
    return value.replace('stm32f1xx','stm32c0xx').replace('stm32f1','stm32c0').replace('Stm32f1','Stm32c0').replace('STM32F1','STM32C0').replace('F103 Ground','C071 candidate')
for path, body in base.items():
    if path.startswith(('Common/','Devices/','Generated/Inc/','Ground/','Interfaces/','Platform/Inc/','Tests/Host/','Tools/','Middlewares/Third_Party/SX1280lib/')):
        files[path] = port(body.decode()).encode() if path.endswith(('.c','.h')) else body
    elif path.startswith('Platform/STM32F1/'):
        if path.endswith('.c') and Path(path).name not in ('platform_critical_stm32f1.c','platform_spi_stm32f1.c','platform_gpio_stm32f1.c','platform_time_stm32f1.c'): continue
        text = port(body.decode())
        # C0 HAL dispatches separate rising/falling callbacks, unlike F1.
        text = text.replace('HAL_GPIO_EXTI_Callback','HAL_GPIO_EXTI_Rising_Callback')
        files[port(path)] = text.encode()
for path in ('Generated/Inc/project_resources.h','Generated/Src/project_resources.c'):
    files[path] = port(base[path].decode()).encode()
files['Generated/Src/pc_byte_stream.c'] = PcUsbCdc_Render().encode()

prefix = 'HardwareGenerated/STClassicC071/'
app = 'Projects/NUCLEO-C071RB/Applications/USB_Device/CDC_Standalone/'
for item in manifest['files']:
    name = item['path']
    if name.startswith(('Drivers/','Middlewares/')) or name in ('README.md','LICENSE.md','Release_Notes.html'):
        files[prefix+name] = (official/name).read_bytes()
    elif name.startswith(app) and name[len(app):].startswith(('Core/','USB_Device/')):
        files[prefix+name[len(app):]] = (official/name).read_bytes()
files[prefix+'startup_stm32c071xx.s'] = (official/'Drivers/CMSIS/Device/ST/STM32C0xx/Source/Templates/gcc/startup_stm32c071xx.s').read_bytes()
for name in ('syscalls',):
    files[prefix+'Core/Src/'+name+'.c'] = (official/(app+'STM32CubeIDE/Application/User/Core/'+name+'.c')).read_bytes()
linker = (official/(app+'STM32CubeIDE/STM32C071RBTX_FLASH.ld')).read_text(encoding='utf-8')
linker = linker.replace('_Min_Heap_Size = 0x200','_Min_Heap_Size = 0x0').replace('_Min_Stack_Size = 0x400','_Min_Stack_Size = 0x800')
files[prefix+'STM32C071FBP6_FLASH.ld'] = linker.encode()

# Preserve the actual official HSI system + HSIUSB48/SOF CRS clock function.
main = (official/(app+'Core/Src/main.c')).read_text(encoding='utf-8')
clock = main[main.index('void SystemClock_Config(void)\n{'):main.index('/**\n  * @brief TIM17')]
notice = main[:main.index('/* USER CODE END Header */')+len('/* USER CODE END Header */')]
files[prefix+'Core/Src/main.c'] = (notice+'''
/* Experimental FBP6 software pin profile; no physical board has been checked. */
#include "main.h"
#include "usb_device.h"
#include "ground_bridge.h"
SPI_HandleTypeDef hspi1;
void SystemClock_Config(void);
static void CandidatePins_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_SPI1_CLK_ENABLE();
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0 | GPIO_PIN_4, GPIO_PIN_SET);
    gpio.Pin = GPIO_PIN_0 | GPIO_PIN_4;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &gpio);
    gpio.Pin = GPIO_PIN_1;
    gpio.Mode = GPIO_MODE_INPUT;
    HAL_GPIO_Init(GPIOA, &gpio);
    gpio.Pin = GPIO_PIN_3;
    gpio.Mode = GPIO_MODE_IT_RISING;
    HAL_GPIO_Init(GPIOA, &gpio);
    HAL_NVIC_SetPriority(EXTI2_3_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(EXTI2_3_IRQn);
    gpio.Pin = GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Alternate = GPIO_AF0_SPI1;
    HAL_GPIO_Init(GPIOA, &gpio);
    hspi1.Instance = SPI1;
    hspi1.Init.Mode = SPI_MODE_MASTER;
    hspi1.Init.Direction = SPI_DIRECTION_2LINES;
    hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
    hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
    hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
    hspi1.Init.NSS = SPI_NSS_SOFT;
    hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;
    hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
    hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
    hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
    hspi1.Init.CRCPolynomial = 7;
    hspi1.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
    if (HAL_SPI_Init(&hspi1) != HAL_OK) { Error_Handler(); }
}
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    CandidatePins_Init();
    MX_USB_Device_Init();
    if (GroundBridge_Init() != GROUND_BRIDGE_OK) { Error_Handler(); }
    while (1) { if (GroundBridge_Process(HAL_GetTick()) != GROUND_BRIDGE_OK) { Error_Handler(); } }
}
void Error_Handler(void) { __disable_irq(); while (1) { } }
''' + clock).encode()
files[prefix+'Core/Src/stm32c0xx_hal_msp.c'] = b'#include "main.h"\nvoid HAL_MspInit(void) { __HAL_RCC_SYSCFG_CLK_ENABLE(); __HAL_RCC_PWR_CLK_ENABLE(); HAL_SYSCFG_DisableRemap(SYSCFG_REMAP_PA11 | SYSCFG_REMAP_PA12); }\n'
files[prefix+'Core/Src/stm32c0xx_it.c'] = b'''#include "main.h"
#include "stm32c0xx_it.h"
extern PCD_HandleTypeDef hpcd_USB_DRD_FS;
void SysTick_Handler(void) { HAL_IncTick(); }
void USB_DRD_FS_IRQHandler(void) { HAL_PCD_IRQHandler(&hpcd_USB_DRD_FS); }
void EXTI2_3_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_3); }
'''
files[prefix+'USB_Device/Target/usbd_conf.c'] = _UsbConf_Integrate(files[prefix+'USB_Device/Target/usbd_conf.c'])

# Replace the official USB-to-UART/TIM demo callback with a bounded SCG CDC
# interface. Original source and its notices remain in the frozen input.
files[prefix+'USB_Device/App/usbd_cdc_if.c'] = (notice+'''
/* SCG candidate CDC interface; no demo UART or TIM17 callbacks. */
#include "usbd_cdc_if.h"
#include "pc_byte_stream.h"
#include <string.h>
extern USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t s_rx[64];
static uint8_t s_idle_tx[1];
static uint8_t s_line[7] = {0x00,0xc2,0x01,0x00,0,0,8};
static int8_t CDC_Init_FS(void)
{
    PcByteStream_OnUsbReset();
    if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, s_idle_tx, 0) != USBD_OK) { return USBD_FAIL; }
    return (int8_t)USBD_CDC_SetRxBuffer(&hUsbDeviceFS, s_rx);
}
static int8_t CDC_DeInit_FS(void) { PcByteStream_OnUsbReset(); return USBD_OK; }
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *data, uint16_t length)
{
    if ((cmd == CDC_SET_LINE_CODING) || (cmd == CDC_GET_LINE_CODING))
    {
        if ((data == NULL) || (length != sizeof(s_line))) { return USBD_FAIL; }
        if (cmd == CDC_SET_LINE_CODING) { memcpy(s_line, data, sizeof(s_line)); }
        else { memcpy(data, s_line, sizeof(s_line)); }
    }
    return USBD_OK;
}
static int8_t CDC_Receive_FS(uint8_t *data, uint32_t *length)
{
    if ((data == NULL) || (length == NULL) || (*length > sizeof(s_rx))) { return USBD_FAIL; }
    PcByteStream_OnUsbReceive(data, (uint16_t)*length);
    if (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, s_rx) != USBD_OK) { return USBD_FAIL; }
    return (int8_t)USBD_CDC_ReceivePacket(&hUsbDeviceFS);
}
static int8_t CDC_TransmitCplt_FS(uint8_t *data, uint32_t *length, uint8_t ep)
{ (void)data; (void)length; (void)ep; return USBD_OK; }
USBD_CDC_ItfTypeDef USBD_Interface_fops_FS = {CDC_Init_FS,CDC_DeInit_FS,CDC_Control_FS,CDC_Receive_FS,CDC_TransmitCplt_FS};
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
    if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, data, length) != USBD_OK) { return USBD_FAIL; }
    return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}
''').encode()
files['Generated/Src/platform_resources.c'] = b'''#include "platform_stm32c0_resources.h"
#include "main.h"
#include <stddef.h>
extern SPI_HandleTypeDef hspi1;
static void * const s_spi_handles[PLATFORM_SPI_COUNT] = {[0U] = &hspi1};
void *PlatformStm32c0Resource_UartHandleGet(PlatformUartId id) { (void)id; return NULL; }
void *PlatformStm32c0Resource_SpiHandleGet(PlatformSpiId id)
{ return ((uint32_t)id < PLATFORM_SPI_COUNT) ? s_spi_handles[id] : NULL; }
static const PlatformStm32c0GpioResource s_gpio_resources[PLATFORM_GPIO_COUNT] =
{
    [0U] = {GPIOA,GPIO_PIN_4,0U},
    [1U] = {GPIOA,GPIO_PIN_0,0U},
    [2U] = {GPIOA,GPIO_PIN_1,0U},
    [3U] = {GPIOA,GPIO_PIN_3,1U}
};
uint8_t PlatformStm32c0Resource_GpioGet(PlatformGpioId id, PlatformStm32c0GpioResource *value)
{
    if (((uint32_t)id >= PLATFORM_GPIO_COUNT) || (value == NULL) || (s_gpio_resources[id].port == NULL)) { return 0U; }
    *value = s_gpio_resources[id]; return 1U;
}
static const PlatformStm32c0TimeResource s_time_resources[PLATFORM_TIME_COUNT] = {[0U] = {1000U}};
uint8_t PlatformStm32c0Resource_TimeGet(PlatformTimeId id, PlatformStm32c0TimeResource *value)
{
    if ((id != (PlatformTimeId)0U) || (value == NULL)) { return 0U; }
    *value = s_time_resources[id]; return 1U;
}
'''
native = args.cubemx.resolve()
if native == output or native.is_relative_to(output) or output.is_relative_to(native):
    raise ValueError('native input and output must be disjoint')
ioc = (native/'C071FBP6_PCD_TEST.ioc').read_text(encoding='utf-8')
for token in ('Mcu.Name=STM32C071FBPx','PB3.GPIO_Label=RADIO_DIO1','USART2.BaudRate=230400','ProjectManager.HeapSize=0x0','ProjectManager.StackSize=0x800'):
    if token not in ioc: raise ValueError('native IOC contract missing: '+token)
native_hashes = {}
for path in sorted(native.rglob('*')):
    if not path.is_file() or 'build' in path.relative_to(native).parts: continue
    if path.is_symlink(): raise ValueError('native symlink forbidden')
    relative = path.relative_to(native).as_posix()
    body = path.read_bytes()
    native_hashes[relative] = hashlib.sha256(body).hexdigest()
    files['NativeCubeMX/'+relative] = body
    if relative.startswith(('Core/Inc/','Drivers/')):
        files[prefix+relative] = body
for name in ('gpio','spi','usart','system_stm32c0xx','stm32c0xx_it'):
    files[prefix+'Core/Src/'+name+'.c'] = (native/'Core/Src'/ (name+'.c')).read_bytes()
files[prefix+'startup_stm32c071xx.s'] = (native/'startup_stm32c071xx.s').read_bytes()
files[prefix+'STM32C071FBP6_FLASH.ld'] = (native/'STM32C071XX_FLASH.ld').read_bytes()
native_main = (native/'Core/Src/main.c').read_text(encoding='utf-8')
native_clock = native_main[native_main.index('void SystemClock_Config(void)\n{'):native_main.index('/* USER CODE BEGIN 4 */')]
main_body = notice+'''\n#include "main.h"
#include "gpio.h"
#include "spi.h"
#include "usart.h"
#include "usb_device.h"
#include "ground_bridge.h"
void SystemClock_Config(void);
int main(void)
{
    if (HAL_Init() != HAL_OK) { Error_Handler(); }
    SystemClock_Config();
    MX_GPIO_Init();
    MX_SPI1_Init();
    MX_USART2_UART_Init();
    MX_USB_Device_Init();
    if (GroundBridge_Init() != GROUND_BRIDGE_OK) { Error_Handler(); }
    while (1) { if (GroundBridge_Process(HAL_GetTick()) != GROUND_BRIDGE_OK) { Error_Handler(); } }
}
void Error_Handler(void) { __disable_irq(); while (1) { } }
'''+native_clock
files[prefix+'Core/Src/main.c'] = main_body.encode()
msp = (native/'Core/Src/stm32c0xx_hal_msp.c').read_text(encoding='utf-8')
msp = msp.replace('__HAL_RCC_PWR_CLK_ENABLE();','__HAL_RCC_PWR_CLK_ENABLE();\n  HAL_SYSCFG_DisableRemap(SYSCFG_REMAP_PA11 | SYSCFG_REMAP_PA12);')
files[prefix+'Core/Src/stm32c0xx_hal_msp.c'] = msp.encode()
usb_conf = files[prefix+'USB_Device/Target/usbd_conf.c'].decode()
# This recipe fixes REGISTER_CALLBACKS=0. Materialize precisely the active
# branch instead of importing an unused runtime registration option.
callback_pattern = r'#if \(USE_HAL_PCD_REGISTER_CALLBACKS == 1U\)\n(.*?)#endif /\* USE_HAL_PCD_REGISTER_CALLBACKS \*/'
def active_callback(match):
    pieces = match.group(1).split('#else\n')
    return pieces[1] if len(pieces) == 2 else ''
usb_conf, branch_count = re.subn(callback_pattern,active_callback,usb_conf,flags=re.S)
if branch_count != 12: raise ValueError('unreviewed classic callback layout')
usb_conf = usb_conf.replace('  return mem;', '  if ((size == 0U) || (size > sizeof(mem))) { return NULL; }\n  return mem;')
for signature, ignored in (('void HAL_PCD_MspDeInit(PCD_HandleTypeDef* hpcd)', 'hpcd'),('void USBD_static_free(void *p)', 'p')):
    # The official hooks intentionally do not consume these arguments.
    usb_conf = usb_conf.replace(signature+'\n{',signature+'\n{\n  (void)'+ignored+';')
files[prefix+'USB_Device/Target/usbd_conf.c'] = usb_conf.encode()
# Authored adapters must enter the renderer's strict/analyzer/Power10 coverage.
adapter_sources = []
for relative in ('Core/Src/main.c','Core/Src/stm32c0xx_hal_msp.c','USB_Device/App/usbd_cdc_if.c','USB_Device/Target/usbd_conf.c'):
    destination = 'Platform/STM32C0/Src/'+Path(relative).name
    files[destination] = files.pop(prefix+relative)
    adapter_sources.append(destination)
files['Generated/Src/platform_resources.c'] = files['Generated/Src/platform_resources.c'].replace(b'{GPIOA,GPIO_PIN_3,1U}',b'{GPIOB,GPIO_PIN_3,1U}')
owned = [path for path in files if path.endswith('.c') and path.startswith(('Common/','Devices/','Generated/','Ground/','Platform/','Middlewares/Third_Party/SX1280lib/'))]
sources = owned + [prefix+'Core/Src/'+name+'.c' for name in ('gpio','spi','usart','system_stm32c0xx','stm32c0xx_it')]
sources += [prefix+'USB_Device/'+name+'.c' for name in ('App/usb_device','App/usbd_desc')]
sources += [prefix+'Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_'+name+'.c' for name in ('hal','hal_rcc','hal_rcc_ex','hal_cortex','hal_gpio','hal_dma','hal_dma_ex','hal_flash','hal_flash_ex','hal_pwr','hal_pwr_ex','hal_pcd','hal_pcd_ex','hal_spi','hal_spi_ex','hal_uart','hal_uart_ex','hal_exti','ll_usb')]
sources += [prefix+'Middlewares/ST/STM32_USB_Device_Library/'+name+'.c' for name in ('Core/Src/usbd_core','Core/Src/usbd_ctlreq','Core/Src/usbd_ioreq','Class/CDC/Src/usbd_cdc')]
includes = ['Ground/Core/Inc','Ground/Protocol/Inc','Platform/Inc','Platform/STM32C0/Inc','Devices/Telemetry/SX1281/Inc','Middlewares/Third_Party/SX1280lib','Generated/Inc','Common/Inc','Interfaces/Inc']
includes += [prefix+name for name in ('Core/Inc','USB_Device/App','USB_Device/Target','Drivers/STM32C0xx_HAL_Driver/Inc','Drivers/STM32C0xx_HAL_Driver/Inc/Legacy','Drivers/CMSIS/Include','Drivers/CMSIS/Device/ST/STM32C0xx/Include','Middlewares/ST/STM32_USB_Device_Library/Core/Inc','Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc')]
defines = ['USE_HAL_DRIVER','STM32C071xx','USE_HAL_PCD_REGISTER_CALLBACKS=0','USBD_CLASS_BOS_ENABLED=0','USBD_USER_REGISTER_CALLBACK=0','AIR_LINK_HAL_BUFFER_SIZE=260','SILVERSTAR_AIR_LINK_ENABLED=1']
flags = ['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft']
graph = {'sources':sources,'asm_sources':[prefix+'startup_stm32c071xx.s'],'include_dirs':includes,'defines':defines,'mcu_flags':flags,'linker_script':prefix+'STM32C071FBP6_FLASH.ld','required_irq_handlers':['SysTick_Handler','USB_DRD_FS_IRQHandler','EXTI2_3_IRQHandler','USART2_IRQHandler'],'complete_cube_import':False,'experimental_standalone_mcu':'STM32C071FBP6','pin_profile_status':'native v2 IOC; hardware unverified','native_files_sha256':native_hashes,'first_party_adapters':adapter_sources,'integration_exception':'native PCD usb.c replaced by pinned classic CDC usbd_conf.c; no normal SCG C0 importer'}
files['Makefile'] = _Makefile_Render(tuple(sources),tuple(graph['asm_sources']),tuple(includes),tuple(defines),SimpleNamespace(**graph),'arm-none-eabi-').encode()
files['Generated/ground_source_graph.json'] = json.dumps(graph,indent=2).encode()
metadata = json.loads(base['Generated/ground_target_metadata.json'])
metadata.update(mcu='STM32C071FBP6',pc_interface='usb_cdc',hardware_fingerprint='native v2 IOC, hardware unverified',input_kind='native CubeMX PCD plus pinned official classic CDC integration')
files['Generated/ground_target_metadata.json'] = json.dumps(metadata,indent=2).encode()
output.mkdir(parents=True,exist_ok=True)
for path,body in files.items():
    destination = output/path; destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(body)
(output/'candidate-manifest.json').write_text(json.dumps({'official_sources':manifest['sources'],'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'mcu':'STM32C071FBP6','mode':'experimental standalone software only','files_sha256':{path:hashlib.sha256(body).hexdigest() for path,body in files.items()}},indent=2))
print('C071 software candidate',len(sources),'C sources',output)
