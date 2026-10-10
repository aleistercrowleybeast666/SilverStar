#include "native_platform.h"
#include "native_clock.h"
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "main.h"
#include <stddef.h>

extern SPI_HandleTypeDef hspi1;
typedef struct { GPIO_TypeDef *port; uint16_t pin; uint8_t output; } NativeGpioBinding;
static const NativeGpioBinding s_gpio_bindings[4] = {
    {GPIOA, GPIO_PIN_4, 1U},
    {GPIOB, GPIO_PIN_11, 1U},
    {GPIOB, GPIO_PIN_10, 0U},
    {GPIOB, GPIO_PIN_0, 0U}
};
static uint8_t s_initialized;
static uint8_t s_spi_active;
static volatile uint8_t s_dio1_pending;
static uint8_t s_tx_copy[260];

PlatformResult NativePlatform_Init(void)
{
    if (s_initialized != 0U) { return PLATFORM_ALREADY_INITIALIZED; }
    if ((hspi1.Instance != SPI1) ||
        (hspi1.Init.Mode != SPI_MODE_MASTER) ||
        (hspi1.Init.Direction != SPI_DIRECTION_2LINES) ||
        (hspi1.Init.DataSize != SPI_DATASIZE_8BIT) ||
        (hspi1.Init.CLKPolarity != SPI_POLARITY_LOW) ||
        (hspi1.Init.CLKPhase != SPI_PHASE_1EDGE) ||
        (hspi1.Init.NSS != SPI_NSS_SOFT) ||
        (hspi1.Init.FirstBit != SPI_FIRSTBIT_MSB) ||
        (hspi1.Init.TIMode != SPI_TIMODE_DISABLE) ||
        (hspi1.Init.CRCCalculation != SPI_CRCCALCULATION_DISABLE) ||
        (hspi1.Init.BaudRatePrescaler != SPI_BAUDRATEPRESCALER_8) ||
        (hspi1.State != HAL_SPI_STATE_READY) ||
        (NativeClock_StatusGet() != NativeClockResult_Ok))
    { return PLATFORM_NOT_READY; }
    s_initialized = 1U;
    return PLATFORM_OK;
}

void NativePlatform_Quiesce(void)
{
    /* Native initialization owns these pins; retire this sole radio owner. */
    HAL_GPIO_WritePin(s_gpio_bindings[0].port, s_gpio_bindings[0].pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(s_gpio_bindings[1].port, s_gpio_bindings[1].pin, GPIO_PIN_RESET);
    s_initialized = 0U;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    uint32_t index = (uint32_t)id;
    if ((index >= 4U) || (high > 1U)) { return PLATFORM_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return PLATFORM_NOT_READY; }
    if (s_gpio_bindings[index].output == 0U) { return PLATFORM_UNSUPPORTED; }
    HAL_GPIO_WritePin(s_gpio_bindings[index].port, s_gpio_bindings[index].pin,
        (high != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    return PLATFORM_OK;
}

PlatformResult PlatformGpio_Read(PlatformGpioId id, uint8_t *high)
{
    uint32_t index = (uint32_t)id;
    if ((index >= 4U) || (high == NULL)) { return PLATFORM_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return PLATFORM_NOT_READY; }
    *high = (HAL_GPIO_ReadPin(s_gpio_bindings[index].port,
             s_gpio_bindings[index].pin) == GPIO_PIN_SET) ? 1U : 0U;
    return PLATFORM_OK;
}

void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    if (pin == s_gpio_bindings[3].pin) { s_dio1_pending = 1U; }
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t pending;
    PlatformCriticalState saved;
    if ((id != PLATFORM_GPIO_3) || (s_initialized == 0U)) { return 0U; }
    saved = PlatformCritical_Enter();
    pending = s_dio1_pending;
    s_dio1_pending = 0U;
    PlatformCritical_Exit(saved);
    return pending;
}

static PlatformResult NativeSpi_ResultGet(HAL_StatusTypeDef result)
{
    switch (result)
    {
        case HAL_OK: return PLATFORM_OK;
        case HAL_BUSY: return PLATFORM_BUSY;
        case HAL_TIMEOUT: return PLATFORM_TIMEOUT;
        case HAL_ERROR: return PLATFORM_IO_ERROR;
        default: return PLATFORM_IO_ERROR;
    }
}

static PlatformResult NativeSpi_Exchange(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout, uint8_t receive,
    PlatformSpiDriverObservation *observation)
{
    uint16_t index;
    HAL_StatusTypeDef result;
    if (observation != NULL) { *observation = (PlatformSpiDriverObservation){0}; }
    if ((id != PLATFORM_SPI_1) || (tx == NULL) || (length == 0U) ||
        (length > sizeof(s_tx_copy)) || (timeout == 0U) || (timeout > 100U) ||
        ((receive != 0U) && (rx == NULL))) { return PLATFORM_INVALID_ARGUMENT; }
    if ((s_initialized == 0U) || (__get_IPSR() != 0U) || (__get_PRIMASK() != 0U))
    { return PLATFORM_NOT_READY; }
    SILVERSTAR_ASSERT(s_spi_active <= 1U, SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_spi_active != 0U) { return PLATFORM_BUSY; }
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    s_spi_active = 1U;
    for (index = 0U; (index < length) && (index < sizeof(s_tx_copy)); index++)
    { s_tx_copy[index] = tx[index]; }
    result = (receive != 0U) ? HAL_SPI_TransmitReceive(&hspi1, s_tx_copy, rx, length, timeout) :
        HAL_SPI_Transmit(&hspi1, s_tx_copy, length, timeout);
    s_spi_active = 0U;
    /* No invented SR value is marked as observed. Native HAL byte ownership
     * and result are checked; register diagnostics need a separate ABI port. */
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    return NativeSpi_ResultGet(result);
}

PlatformResult PlatformSpi_WriteObserved(PlatformSpiId id, const uint8_t *data,
    uint16_t length, uint32_t timeout, PlatformSpiDriverObservation *observation)
{ return NativeSpi_Exchange(id, data, NULL, length, timeout, 0U, observation); }

PlatformResult PlatformSpi_TransferObserved(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout, PlatformSpiDriverObservation *observation)
{ return NativeSpi_Exchange(id, tx, rx, length, timeout, 1U, observation); }

PlatformResult PlatformSpi_Write(PlatformSpiId id, const uint8_t *data,
    uint16_t length, uint32_t timeout)
{ return PlatformSpi_WriteObserved(id, data, length, timeout, NULL); }

PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout)
{ return PlatformSpi_TransferObserved(id, tx, rx, length, timeout, NULL); }
