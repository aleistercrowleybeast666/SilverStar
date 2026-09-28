#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "platform_can.h"
#include "platform_i2c.h"
#include "platform_pwm.h"
#include "platform_stm32f4_resources.h"
#include "stm32f4xx_hal.h"

static I2C_HandleTypeDef s_i2c;
static CAN_HandleTypeDef s_can;
static TIM_TypeDef s_timer_registers;
static TIM_HandleTypeDef s_timer = {&s_timer_registers, {999U}};
static TIM_TypeDef s_small_timer_registers;
static TIM_HandleTypeDef s_small_timer = {&s_small_timer_registers, {99U}};
static HAL_StatusTypeDef s_result = HAL_OK;
static uint16_t s_i2c_address;
static uint16_t s_memory_address;
static uint16_t s_memory_address_size;
static CAN_TxHeaderTypeDef s_tx_header;
static uint32_t s_mailbox_free = 1U;
static uint32_t s_rx_ready;
static uint32_t s_tick;
static uint32_t s_compare[5];
static uint32_t s_pwm_channel;

void *PlatformStm32f4Resource_I2cHandleGet(PlatformI2cId id)
{
    return (id == PLATFORM_I2C_1) ? &s_i2c : NULL;
}

void *PlatformStm32f4Resource_CanHandleGet(PlatformCanId id)
{
    return (id == PLATFORM_CAN_1) ? &s_can : NULL;
}

uint8_t PlatformStm32f4Resource_PwmGet(
    PlatformPwmId id, PlatformStm32f4PwmResource *resource)
{
    static const uint32_t channels[5] = {
        TIM_CHANNEL_1, TIM_CHANNEL_2, TIM_CHANNEL_3,
        TIM_CHANNEL_4, TIM_CHANNEL_1
    };
    static const PlatformPwmMode modes[5] = {
        PLATFORM_PWM_MODE_1, PLATFORM_PWM_MODE_1,
        PLATFORM_PWM_MODE_2, PLATFORM_PWM_MODE_2,
        PLATFORM_PWM_MODE_1
    };
    static const uint8_t active_high[5] = {1U, 0U, 1U, 0U, 1U};
    uint32_t index = (uint32_t)id;

    if ((resource == NULL) || (index >= 5U)) { return 0U; }
    resource->handle = (index == 4U) ? &s_small_timer : &s_timer;
    resource->channel = channels[index];
    resource->frequency_hz = 1000U;
    resource->resolution_bits = 9U;
    resource->mode = modes[index];
    resource->active_high = active_high[index];
    return 1U;
}

HAL_StatusTypeDef HAL_I2C_Master_Transmit(
    I2C_HandleTypeDef *handle, uint16_t address, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    assert(handle == &s_i2c);
    assert(data != NULL);
    assert(length > 0U);
    assert(timeout_ms > 0U);
    s_i2c_address = address;
    return s_result;
}

HAL_StatusTypeDef HAL_I2C_Master_Receive(
    I2C_HandleTypeDef *handle, uint16_t address, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    return HAL_I2C_Master_Transmit(handle, address, data, length, timeout_ms);
}

HAL_StatusTypeDef HAL_I2C_Mem_Write(
    I2C_HandleTypeDef *handle, uint16_t address, uint16_t memory_address,
    uint16_t memory_address_size, uint8_t *data, uint16_t length,
    uint32_t timeout_ms)
{
    s_memory_address = memory_address;
    s_memory_address_size = memory_address_size;
    return HAL_I2C_Master_Transmit(
        handle, address, data, length, timeout_ms);
}

HAL_StatusTypeDef HAL_I2C_Mem_Read(
    I2C_HandleTypeDef *handle, uint16_t address, uint16_t memory_address,
    uint16_t memory_address_size, uint8_t *data, uint16_t length,
    uint32_t timeout_ms)
{
    return HAL_I2C_Mem_Write(
        handle, address, memory_address, memory_address_size,
        data, length, timeout_ms);
}

HAL_StatusTypeDef HAL_CAN_Start(CAN_HandleTypeDef *handle)
{
    assert(handle == &s_can);
    return s_result;
}

HAL_StatusTypeDef HAL_CAN_Stop(CAN_HandleTypeDef *handle)
{
    return HAL_CAN_Start(handle);
}

uint32_t HAL_CAN_GetError(CAN_HandleTypeDef *handle)
{
    assert(handle == &s_can);
    return 0U;
}

uint32_t HAL_CAN_GetTxMailboxesFreeLevel(CAN_HandleTypeDef *handle)
{
    assert(handle == &s_can);
    return s_mailbox_free;
}

HAL_StatusTypeDef HAL_CAN_AddTxMessage(
    CAN_HandleTypeDef *handle, CAN_TxHeaderTypeDef *header,
    uint8_t *data, uint32_t *mailbox)
{
    assert(handle == &s_can);
    assert(data != NULL);
    assert(mailbox != NULL);
    s_tx_header = *header;
    return s_result;
}

uint32_t HAL_CAN_GetRxFifoFillLevel(
    CAN_HandleTypeDef *handle, uint32_t fifo)
{
    assert(handle == &s_can);
    assert(fifo == CAN_RX_FIFO0);
    return s_rx_ready;
}

HAL_StatusTypeDef HAL_CAN_GetRxMessage(
    CAN_HandleTypeDef *handle, uint32_t fifo,
    CAN_RxHeaderTypeDef *header, uint8_t *data)
{
    assert(handle == &s_can);
    assert(fifo == CAN_RX_FIFO0);
    (void)memset(header, 0, sizeof(*header));
    header->StdId = 0x321U;
    header->IDE = CAN_ID_STD;
    header->DLC = 2U;
    data[0] = 0x12U;
    data[1] = 0x34U;
    return s_result;
}

uint32_t HAL_GetTick(void)
{
    return s_tick++;
}

HAL_StatusTypeDef HAL_TIM_PWM_Start(
    TIM_HandleTypeDef *handle, uint32_t channel)
{
    assert(handle == &s_timer);
    s_pwm_channel = channel;
    return s_result;
}

HAL_StatusTypeDef HAL_TIM_PWM_Stop(
    TIM_HandleTypeDef *handle, uint32_t channel)
{
    return HAL_TIM_PWM_Start(handle, channel);
}

void TestHal_TimCompareSet(
    TIM_HandleTypeDef *handle, uint32_t channel, uint32_t compare)
{
    assert((handle == &s_timer) || (handle == &s_small_timer));
    s_pwm_channel = channel;
    s_compare[channel / 4U] = compare;
}

static uint32_t PlatformPwm_ModeGet(uint32_t channel)
{
    if (channel == TIM_CHANNEL_1)
    {
        return s_timer_registers.CCMR1 & TIM_CCMR1_OC1M;
    }
    if (channel == TIM_CHANNEL_2)
    {
        return (s_timer_registers.CCMR1 & TIM_CCMR1_OC2M) >> 8U;
    }
    if (channel == TIM_CHANNEL_3)
    {
        return s_timer_registers.CCMR2 & TIM_CCMR2_OC3M;
    }
    return (s_timer_registers.CCMR2 & TIM_CCMR2_OC4M) >> 8U;
}

static void PlatformI2c_Test(void)
{
    uint8_t buffer[4] = {0x12U, 0x34U, 0U, 0U};

    assert(PlatformI2c_Write(
        PLATFORM_I2C_1, 0x68U, buffer, 2U, 10U) == PLATFORM_OK);
    assert(s_i2c_address == 0xD0U);
    assert(PlatformI2c_Write(
        PLATFORM_I2C_1, 0x07U, buffer, 2U, 10U) ==
        PLATFORM_INVALID_ARGUMENT);
    assert(PlatformI2c_Write(
        PLATFORM_I2C_1, 0x68U, NULL, 2U, 10U) ==
        PLATFORM_INVALID_ARGUMENT);
    assert(PlatformI2c_Read(
        PLATFORM_I2C_1, 0x68U, buffer, 0U, 10U) ==
        PLATFORM_INVALID_ARGUMENT);
    assert(PlatformI2c_Read(
        PLATFORM_I2C_1, 0x68U, buffer, 1U, 0U) ==
        PLATFORM_INVALID_ARGUMENT);
    s_result = HAL_BUSY;
    assert(PlatformI2c_Read(
        PLATFORM_I2C_1, 0x68U, buffer, 1U, 10U) == PLATFORM_BUSY);
    s_result = HAL_TIMEOUT;
    assert(PlatformI2c_Read(
        PLATFORM_I2C_1, 0x68U, buffer, 1U, 10U) == PLATFORM_TIMEOUT);
    s_result = HAL_OK;
    assert(PlatformI2c_MemoryRead(
        PLATFORM_I2C_1, 0x68U, 0x12U,
        PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, buffer, 2U, 10U) == PLATFORM_OK);
    assert(s_memory_address == 0x12U);
    assert(s_memory_address_size == I2C_MEMADD_SIZE_8BIT);
    assert(PlatformI2c_MemoryWrite(
        PLATFORM_I2C_1, 0x68U, 0x1234U,
        PLATFORM_I2C_MEMORY_ADDRESS_16_BIT, buffer, 2U, 10U) == PLATFORM_OK);
    assert(s_memory_address == 0x1234U);
    assert(s_memory_address_size == I2C_MEMADD_SIZE_16BIT);
    assert(PlatformI2c_MemoryRead(
        PLATFORM_I2C_1, 0x68U, 0x12U,
        (PlatformI2cMemoryAddressSize)99, buffer, 2U, 10U) ==
        PLATFORM_INVALID_ARGUMENT);
}

static void PlatformCan_Test(void)
{
    PlatformCanFrame frame = {0x123U, 2U, 0U, {1U, 2U}};
    PlatformCanDiagnostics diagnostics;

    assert(PlatformCan_Start(PLATFORM_CAN_1) == PLATFORM_OK);
    assert(PlatformCan_Start(PLATFORM_CAN_COUNT) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformCan_Send(PLATFORM_CAN_1, &frame, 10U) == PLATFORM_OK);
    assert(s_tx_header.StdId == 0x123U);
    assert(s_tx_header.DLC == 2U);
    frame.length = 9U;
    assert(PlatformCan_Send(
        PLATFORM_CAN_1, &frame, 10U) == PLATFORM_INVALID_ARGUMENT);
    frame.length = 2U;
    frame.identifier = 0x800U;
    assert(PlatformCan_Send(
        PLATFORM_CAN_1, &frame, 10U) == PLATFORM_INVALID_ARGUMENT);
    frame.identifier = 0x123U;
    s_mailbox_free = 0U;
    s_tick = 0U;
    assert(PlatformCan_Send(PLATFORM_CAN_1, &frame, 2U) == PLATFORM_TIMEOUT);
    s_mailbox_free = 1U;
    s_rx_ready = 0U;
    assert(PlatformCan_ReceivePoll(
        PLATFORM_CAN_1, &frame) == PLATFORM_NOT_READY);
    s_rx_ready = 1U;
    assert(PlatformCan_ReceivePoll(PLATFORM_CAN_1, &frame) == PLATFORM_OK);
    assert((frame.identifier == 0x321U) && (frame.length == 2U));
    assert(PlatformCan_DiagnosticsGet(
        PLATFORM_CAN_1, &diagnostics) == PLATFORM_OK);
    assert((diagnostics.tx_count == 1U) && (diagnostics.rx_count == 1U));
}

static void PlatformPwm_Test(void)
{
    PlatformPwmDiagnostics diagnostics;
    const PlatformPwmId ids[4] = {
        PLATFORM_PWM_1, PLATFORM_PWM_2,
        PLATFORM_PWM_3, PLATFORM_PWM_4
    };
    const uint32_t channels[4] = {
        TIM_CHANNEL_1, TIM_CHANNEL_2,
        TIM_CHANNEL_3, TIM_CHANNEL_4
    };
    const uint32_t intermediate_modes[4] = {
        TIM_OCMODE_PWM1, TIM_OCMODE_PWM1,
        TIM_OCMODE_PWM2, TIM_OCMODE_PWM2
    };
    uint32_t index;

    for (index = 0U; index < 4U; index++)
    {
        assert(PlatformPwm_Start(ids[index]) == PLATFORM_OK);
        assert(s_pwm_channel == channels[index]);
        assert(PlatformPwm_ModeGet(channels[index]) ==
               TIM_OCMODE_FORCED_INACTIVE);
        assert(PlatformPwm_DutyPermilleSet(ids[index], 1U) == PLATFORM_OK);
        assert(s_compare[index] == ((index < 2U) ? 1U : 999U));
        assert(PlatformPwm_ModeGet(channels[index]) ==
               intermediate_modes[index]);
        assert(PlatformPwm_DutyPermilleSet(ids[index], 500U) == PLATFORM_OK);
        assert(s_compare[index] == 500U);
        assert(PlatformPwm_DutyPermilleSet(ids[index], 999U) == PLATFORM_OK);
        assert(s_compare[index] == ((index < 2U) ? 999U : 1U));
        assert(PlatformPwm_DutyPermilleSet(ids[index], 1000U) == PLATFORM_OK);
        assert(s_compare[index] == 999U);
        assert(PlatformPwm_ModeGet(channels[index]) ==
               TIM_OCMODE_FORCED_ACTIVE);
        assert(PlatformPwm_SafeInactiveSet(ids[index]) == PLATFORM_OK);
        assert(s_compare[index] == 0U);
        assert(PlatformPwm_ModeGet(channels[index]) ==
               TIM_OCMODE_FORCED_INACTIVE);
    }
    assert(PlatformPwm_DutyPermilleSet(
        PLATFORM_PWM_1, 1001U) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformPwm_DutyPermilleSet(
        PLATFORM_PWM_5, 1U) == PLATFORM_UNSUPPORTED);
    assert(PlatformPwm_DiagnosticsGet(
        PLATFORM_PWM_2, &diagnostics) == PLATFORM_OK);
    assert((diagnostics.frequency_hz == 1000U) &&
           (diagnostics.resolution_bits == 9U) &&
           (diagnostics.active_high == 0U) &&
           (diagnostics.started == 0U));
}

int main(void)
{
    PlatformI2c_Test();
    PlatformCan_Test();
    PlatformPwm_Test();
    return 0;
}
