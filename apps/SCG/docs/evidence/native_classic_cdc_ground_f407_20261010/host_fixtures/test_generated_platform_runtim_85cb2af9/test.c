#include "main.h"
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
void SX1280HalWakeup(uint8_t instance)
{
    SX1280HalTransfer_Validate(instance, NULL, 0U, 2U);
    /* Native bare-metal main is the sole radio/SPI owner; DIO ISR only
     * records a flag. Keep tick/USB IRQs live through SPI and Busy waits. */
    SILVERSTAR_ASSERT(NativeClock_ContextAllowedGet() != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    uint16_t hal_size = 2U;

    GpioWrite(instance, RADIO_NSS, 0U);
    SX1280_HAL_TX_BUFFER[0] = RADIO_GET_STATUS;
    SX1280_HAL_TX_BUFFER[1] = 0U;
    SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);

}
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
