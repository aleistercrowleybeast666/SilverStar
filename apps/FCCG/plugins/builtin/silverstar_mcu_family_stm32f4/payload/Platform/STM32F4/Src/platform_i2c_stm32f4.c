#include "platform_i2c.h"

#include <stddef.h>

#include "platform_stm32f4_resources.h"
#include "silverstar_assert.h"
#include "stm32f4xx_hal.h"

static I2C_HandleTypeDef *PlatformI2c_HandleGet(PlatformI2cId id)
{
    return (I2C_HandleTypeDef *)PlatformStm32f4Resource_I2cHandleGet(id);
}

static uint8_t *PlatformI2c_HalBufferGet(const uint8_t *data)
{
    return (uint8_t *)(uintptr_t)data;
}

static PlatformResult PlatformI2c_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    return PLATFORM_IO_ERROR;
}

static uint8_t PlatformI2c_ArgumentsValid(uint16_t address_7bit,
                                          const void *data,
                                          uint16_t length,
                                          uint32_t timeout_ms)
{
    return ((address_7bit >= 0x08U) && (address_7bit <= 0x77U) &&
            (data != NULL) &&
            (length > 0U) && (timeout_ms > 0U)) ? 1U : 0U;
}

static uint16_t PlatformI2c_HalAddressGet(uint16_t address_7bit)
{
    return (uint16_t)(address_7bit << 1U);
}

static PlatformResult PlatformI2c_HalMemoryAddressSizeGet(
    PlatformI2cMemoryAddressSize size, uint16_t *hal_size)
{
    if (hal_size == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    if (size == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT)
    {
        *hal_size = I2C_MEMADD_SIZE_8BIT;
        return PLATFORM_OK;
    }
    if (size == PLATFORM_I2C_MEMORY_ADDRESS_16_BIT)
    {
        *hal_size = I2C_MEMADD_SIZE_16BIT;
        return PLATFORM_OK;
    }
    return PLATFORM_INVALID_ARGUMENT;
}

PlatformResult PlatformI2c_Write(PlatformI2cId id,
                                 uint16_t address_7bit,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t timeout_ms)
{
    I2C_HandleTypeDef *handle = PlatformI2c_HandleGet(id);

    if ((handle == NULL) ||
        (PlatformI2c_ArgumentsValid(address_7bit, data, length,
                                    timeout_ms) == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformI2c_ResultMap(HAL_I2C_Master_Transmit(
        handle, PlatformI2c_HalAddressGet(address_7bit),
        PlatformI2c_HalBufferGet(data), length, timeout_ms));
}

PlatformResult PlatformI2c_Read(PlatformI2cId id,
                                uint16_t address_7bit,
                                uint8_t *data,
                                uint16_t length,
                                uint32_t timeout_ms)
{
    I2C_HandleTypeDef *handle = PlatformI2c_HandleGet(id);

    if ((handle == NULL) ||
        (PlatformI2c_ArgumentsValid(address_7bit, data, length,
                                    timeout_ms) == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformI2c_ResultMap(HAL_I2C_Master_Receive(
        handle, PlatformI2c_HalAddressGet(address_7bit), data, length,
        timeout_ms));
}

PlatformResult PlatformI2c_MemoryWrite(
    PlatformI2cId id, uint16_t address_7bit,
    uint16_t memory_address, PlatformI2cMemoryAddressSize memory_address_size,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms)
{
    I2C_HandleTypeDef *handle = PlatformI2c_HandleGet(id);
    uint16_t hal_memory_address_size;

    if ((handle == NULL) ||
        (PlatformI2c_HalMemoryAddressSizeGet(
             memory_address_size, &hal_memory_address_size) != PLATFORM_OK) ||
        (PlatformI2c_ArgumentsValid(address_7bit, data, length,
                                    timeout_ms) == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformI2c_ResultMap(HAL_I2C_Mem_Write(
        handle, PlatformI2c_HalAddressGet(address_7bit), memory_address,
        hal_memory_address_size, PlatformI2c_HalBufferGet(data), length,
        timeout_ms));
}

PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id,
                                      uint16_t address_7bit,
                                      uint16_t memory_address,
                                      PlatformI2cMemoryAddressSize memory_address_size,
                                      uint8_t *data,
                                      uint16_t length,
                                      uint32_t timeout_ms)
{
    I2C_HandleTypeDef *handle = PlatformI2c_HandleGet(id);
    uint16_t hal_memory_address_size;

    if ((handle == NULL) ||
        (PlatformI2c_HalMemoryAddressSizeGet(
             memory_address_size, &hal_memory_address_size) != PLATFORM_OK) ||
        (PlatformI2c_ArgumentsValid(address_7bit, data, length,
                                    timeout_ms) == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(handle, I2C_HandleTypeDef,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    SILVERSTAR_ASSERT_OBJECT(data, uint8_t,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    return PlatformI2c_ResultMap(HAL_I2C_Mem_Read(
        handle, PlatformI2c_HalAddressGet(address_7bit), memory_address,
        hal_memory_address_size, data, length, timeout_ms));
}
