from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_radio import NativeRadioHal_Derive
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.hardware.native_classic_cdc import NativeClassicCdc_Inspect
from silverstar_fccg.generator.native_platform import NativePlatformContract_Inspect, NativePlatform_FilesRender
from test_native_classic_cdc import native


def test_actual_native_platform_contract(native):
    root, args = native
    proof, inventory, files = NativeClassicCdc_Inspect(root, **args)
    contract = NativePlatformContract_Inspect(files, proof, inventory)
    spi = next(item for item in inventory.HardwareResources_Get() if item.resource_id == proof['bindings']['spi'])
    assert contract['spi_clock_hz'] == spi.metadata['clock_hz']
    handler = 'EXTI0_IRQHandler' if args['device_facts'].core == 'cortex-m3' else 'EXTI9_5_IRQHandler'
    assert contract['dio1_irq']['handler'] == handler
    assert contract['dio1_irq']['irq_number'] == proof['independent_irq_slots'][handler]
    assert len(NativePlatform_FilesRender(contract)) == 2


@pytest.mark.parametrize('mutation', ['prescaler', 'expression', 'dio-irq', 'dio-route', 'spi-pin', 'callback'])
def test_native_platform_conflicting_owner_rejected(native, mutation):
    root, args = native
    proof, inventory, files = NativeClassicCdc_Inspect(root, **args)
    original_contract = NativePlatformContract_Inspect(files, proof, inventory)
    irq = original_contract['dio1_irq']['handler'].replace('_IRQHandler','_IRQn')
    changes = {
        'prescaler': ('Core/Src/spi.c', b'SPI_BAUDRATEPRESCALER_8', b'SPI_BAUDRATEPRESCALER_16'),
        'expression': ('Core/Src/spi.c', b'SPI_MODE_MASTER;', b'(1 ? SPI_MODE_SLAVE : SPI_MODE_MASTER);'),
        'dio-irq': ('Core/Src/gpio.c', ('HAL_NVIC_EnableIRQ('+irq+');').encode(), ('HAL_NVIC_DisableIRQ('+irq+');').encode()),
        'dio-route': ('Core/Src/stm32f1xx_it.c' if args['device_facts'].core == 'cortex-m3' else 'Core/Src/stm32f4xx_it.c',
                      b'HAL_GPIO_EXTI_IRQHandler(RADIO_DIO1_Pin);', b'HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_1);'),
        'spi-pin': ('Core/Src/spi.c', b'GPIO_MODE_AF_PP;', b'GPIO_MODE_OUTPUT_PP;'),
    }
    if mutation == 'callback':
        files['Core/Src/gpio.c'] += b'\nvoid HAL_GPIO_EXTI_Callback(uint16_t pin) { (void)pin; }\n'
    else:
        path, before, after = changes[mutation]
        # Both fixture prescalers are independently specified in the inventory.
        if mutation == 'prescaler' and before not in files[path]:
            before = contract_prescaler = NativePlatformContract_Inspect(files, proof, inventory)['spi_initializers']['BaudRatePrescaler'].encode()
            after = b'SPI_BAUDRATEPRESCALER_2' if contract_prescaler != b'SPI_BAUDRATEPRESCALER_2' else b'SPI_BAUDRATEPRESCALER_4'
        assert before in files[path]
        files[path] = files[path].replace(before, after)
    with pytest.raises(ValueError):
        NativePlatformContract_Inspect(files, proof, inventory)


def test_generated_platform_runtime_boundaries(tmp_path):
    compiler = shutil.which('gcc')
    if compiler is None:
        pytest.skip('Host GCC unavailable')
    contract = {'spi_handle':'hspi1', 'spi_peripheral':'SPI1',
        'spi_initializers':{'BaudRatePrescaler':'SPI_BAUDRATEPRESCALER_8'},
        'gpio':[{'role':role,'port':port,'pin':pin} for role,port,pin in (
            ('nss','GPIOA','GPIO_PIN_4'),('reset','GPIOB','GPIO_PIN_11'),
            ('busy','GPIOB','GPIO_PIN_10'),('dio1','GPIOB','GPIO_PIN_0'))]}
    for path, content in NativePlatform_FilesRender(contract).items():
        dest = tmp_path/path; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(content)
    (tmp_path/'native_clock.h').write_text('''#include <stdint.h>
typedef enum { NativeClockResult_Ok, NativeClockResult_Stopped } NativeClockResult;
NativeClockResult NativeClock_StatusGet(void);
NativeClockResult NativeClock_DelayUs(uint32_t delay);
uint8_t NativeClock_ContextAllowedGet(void);
''',encoding='utf-8')
    (tmp_path/'silverstar_assert.h').write_text('''#include <assert.h>
#define SILVERSTAR_ASSERT_MODULE_GENERATED 1U
#define SILVERSTAR_ASSERT_REASON_STATE_INVARIANT 1U
#define SILVERSTAR_ASSERT_MODULE_DEVICE 2U
#define SILVERSTAR_ASSERT(p,m,r) assert(p)
''',encoding='utf-8')
    (tmp_path/'main.h').write_text('''#ifndef HOST_MAIN_H
#define HOST_MAIN_H
#include <stdint.h>
typedef enum { HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { GPIO_PIN_RESET,GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t value; } GPIO_TypeDef;
typedef struct { uint32_t Mode,Direction,DataSize,CLKPolarity,CLKPhase,NSS,FirstBit,TIMode,CRCCalculation,BaudRatePrescaler; } SpiInit;
typedef struct { void *Instance; SpiInit Init; uint32_t State; } SPI_HandleTypeDef;
extern GPIO_TypeDef gpioa,gpiob;
#define GPIOA (&gpioa)
#define GPIOB (&gpiob)
#define SPI1 ((void *)GPIOA)
#define GPIO_PIN_4 16U
#define GPIO_PIN_11 2048U
#define GPIO_PIN_10 1024U
#define GPIO_PIN_0 1U
#define SPI_MODE_MASTER 1U
#define SPI_DIRECTION_2LINES 1U
#define SPI_DATASIZE_8BIT 1U
#define SPI_POLARITY_LOW 1U
#define SPI_PHASE_1EDGE 1U
#define SPI_NSS_SOFT 1U
#define SPI_FIRSTBIT_MSB 1U
#define SPI_TIMODE_DISABLE 1U
#define SPI_CRCCALCULATION_DISABLE 1U
#define SPI_BAUDRATEPRESCALER_8 1U
#define HAL_SPI_STATE_READY 1U
uint32_t __get_IPSR(void);
uint32_t __get_PRIMASK(void);
void HAL_GPIO_EXTI_Callback(uint16_t pin);
void HAL_GPIO_WritePin(GPIO_TypeDef *,uint16_t,GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *,uint16_t);
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *,uint8_t *,uint16_t,uint32_t);
HAL_StatusTypeDef HAL_SPI_TransmitReceive(SPI_HandleTypeDef *,uint8_t *,uint8_t *,uint16_t,uint32_t);
#endif
''',encoding='utf-8')
    harness = '''#include "main.h"
#include "native_platform.h"
#include "native_clock.h"
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include <assert.h>
#include <string.h>
GPIO_TypeDef gpioa,gpiob;
SPI_HandleTypeDef hspi1={SPI1,{1U,1U,1U,1U,1U,1U,1U,1U,1U,1U},1U};
static uint32_t mask,ipsr,calls; static uint8_t clock_fail_after;
static NativeClockResult clock_result=NativeClockResult_Ok;
static HAL_StatusTypeDef hal_result=HAL_OK;
uint32_t __get_IPSR(void) { return ipsr; }
uint32_t __get_PRIMASK(void) { return mask; }
PlatformCriticalState PlatformCritical_Enter(void) { uint32_t saved=mask;mask=1U;return saved; }
void PlatformCritical_Exit(PlatformCriticalState saved) { mask=saved; }
NativeClockResult NativeClock_StatusGet(void) { return clock_result; }
NativeClockResult NativeClock_DelayUs(uint32_t delay) { assert(delay==1U);return clock_result; }
uint8_t NativeClock_ContextAllowedGet(void) { return (mask==0U && ipsr==0U) ? 1U : 0U; }
void HAL_GPIO_WritePin(GPIO_TypeDef *port,uint16_t pin,GPIO_PinState state)
{ if (state==GPIO_PIN_SET) { port->value|=pin; } else { port->value&=~(uint32_t)pin; } }
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port,uint16_t pin)
{ return (port->value&pin)!=0U ? GPIO_PIN_SET : GPIO_PIN_RESET; }
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *spi,uint8_t *tx,uint16_t length,uint32_t timeout)
{ assert(spi==&hspi1 && tx!=NULL && length>0U && timeout>0U);calls++;
  if (clock_fail_after!=0U) { clock_result=NativeClockResult_Stopped; } return hal_result; }
HAL_StatusTypeDef HAL_SPI_TransmitReceive(SPI_HandleTypeDef *spi,uint8_t *tx,uint8_t *rx,uint16_t length,uint32_t timeout)
{ HAL_StatusTypeDef result=HAL_SPI_Transmit(spi,tx,length,timeout); if (result==HAL_OK) { memcpy(rx,tx,length); }return result; }
static uint8_t wake_tx[260];
#define SX1280_HAL_TX_BUFFER wake_tx
#define RADIO_GET_STATUS 0xC0U
#define RADIO_NSS PLATFORM_GPIO_0
static PlatformResult wake_result;
void SX1280HalWakeup(uint8_t instance);
static void SX1280HalTransfer_Validate(uint8_t instance,const uint8_t *buffer,uint16_t size,uint16_t overhead)
{ assert(instance==0U && buffer==NULL && size==0U && overhead==2U); }
static void GpioWrite(uint8_t instance,PlatformGpioId id,uint8_t high)
{ assert(instance==0U && PlatformGpio_Write(id,high)==PLATFORM_OK); }
static void SpiIn(uint8_t instance,const uint8_t *buffer,uint16_t size)
{ assert(instance==0U);wake_result=PlatformSpi_Write(PLATFORM_SPI_1,buffer,size,100U); }
static void SX1280HalWaitOnBusy(uint8_t instance)
{ assert(instance==0U && NativeClock_ContextAllowedGet()!=0U); }
@WAKEUP@
int main(void)
{
    uint8_t tx[262]={0xCAU,1U,2U},rx[262]={0xBEU},high=0xFFU;
    PlatformSpiDriverObservation observed={.valid=1U};tx[261]=0xFEU;rx[261]=0xEFU;
    assert(PlatformGpio_Read(PLATFORM_GPIO_2,&high)==PLATFORM_NOT_READY && high==0xFFU);
    hspi1.Init.BaudRatePrescaler=2U;
    assert(NativePlatform_Init()==PLATFORM_NOT_READY);hspi1.Init.BaudRatePrescaler=1U;
    assert(NativePlatform_Init()==PLATFORM_OK && NativePlatform_Init()==PLATFORM_ALREADY_INITIALIZED);
    SX1280HalWakeup(0U);assert(wake_result==PLATFORM_OK && mask==0U);
    assert(PlatformGpio_Write(PLATFORM_GPIO_0,1U)==PLATFORM_OK && gpioa.value==GPIO_PIN_4);
    assert(PlatformGpio_Write(PLATFORM_GPIO_2,1U)==PLATFORM_UNSUPPORTED);
    assert(PlatformGpio_Read((PlatformGpioId)96,&high)==PLATFORM_INVALID_ARGUMENT && high==0xFFU);
    HAL_GPIO_EXTI_Callback(GPIO_PIN_4);assert(PlatformGpio_IrqConsume(PLATFORM_GPIO_3)==0U);
    HAL_GPIO_EXTI_Callback(GPIO_PIN_0);mask=1U;
    assert(PlatformGpio_IrqConsume(PLATFORM_GPIO_3)==1U && mask==1U);
    assert(PlatformGpio_IrqConsume(PLATFORM_GPIO_3)==0U);mask=0U;
    assert(PlatformSpi_TransferObserved(PLATFORM_SPI_1,&tx[1],&rx[1],260U,100U,&observed)==PLATFORM_OK);
    assert(observed.valid==0U && memcmp(&tx[1],&rx[1],260U)==0);
    assert(tx[0]==0xCAU && tx[261]==0xFEU && rx[0]==0xBEU && rx[261]==0xEFU);
    assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,261U,100U)==PLATFORM_INVALID_ARGUMENT);
    ipsr=1U;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_NOT_READY);ipsr=0U;
    mask=1U;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_NOT_READY);mask=0U;
    hal_result=HAL_TIMEOUT;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_TIMEOUT);
    hal_result=HAL_ERROR;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_IO_ERROR);
    hal_result=HAL_BUSY;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_BUSY);
    hal_result=HAL_OK;clock_fail_after=1U;
    assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_NOT_READY);
    uint32_t before=calls;assert(PlatformSpi_Write(PLATFORM_SPI_1,tx,1U,100U)==PLATFORM_NOT_READY && calls==before);
    NativePlatform_Quiesce();assert(gpioa.value==GPIO_PIN_4 && (gpiob.value&GPIO_PIN_11)==0U);
    assert(PlatformGpio_Write(PLATFORM_GPIO_0,0U)==PLATFORM_NOT_READY);
    return 0;
}
'''
    radio_source=(Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_device_telemetry_sx1281/payload/Middlewares/Third_Party/SX1280lib/sx1280-hal.c').read_bytes()
    derived=NativeRadioHal_Derive(radio_source).decode()
    start,_opening,end=NativeC_FunctionSpanGet(derived,'SX1280HalWakeup')
    (tmp_path/'test.c').write_text(harness.replace('@WAKEUP@',derived[start:end]),encoding='utf-8')
    api=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion',
        '-Wsign-conversion','-Wshadow','-Wundef','-Wcast-qual','-Wstrict-prototypes','-Wmissing-prototypes',
        '-Wswitch-enum','-fanalyzer','-I'+str(tmp_path),'-I'+str(api),'-I'+str(tmp_path/'Generated/Inc'),
        str(tmp_path/'Generated/Src/native_platform.c'),str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    run=subprocess.run([str(tmp_path/'test.exe')],capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr
