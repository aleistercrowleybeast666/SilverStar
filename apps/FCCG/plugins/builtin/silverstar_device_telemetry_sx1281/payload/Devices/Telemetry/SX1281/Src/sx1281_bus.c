#include "sx1281_bus.h"

#include <stddef.h>

#include "project_resources.h"
#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "silverstar_assert.h"
#include "sx1281_config.h"

#define SX1281_BUSY_POLL_GUARD 1000000UL

static Sx1281BusStatus s_bus_status[PROJECT_SX1281_INSTANCE_COUNT];

static uint8_t Sx1281Bus_ResourcesGet(
    uint8_t instance, ProjectSx1281Resources *resources)
{
    if ((resources == NULL) ||
        (ProjectSx1281Resources_Get(instance, resources) != SYSTEM_DEVICE_OK))
    {
        return 0U;
    }
    return 1U;
}

void Sx1281Bus_Init(uint8_t instance)
{
    if (instance >= PROJECT_SX1281_INSTANCE_COUNT) { return; }
    s_bus_status[instance].last_result = SX1281_BUS_OK;
    s_bus_status[instance].spi_error_count = 0U;
    s_bus_status[instance].spi_timeout_count = 0U;
    s_bus_status[instance].busy_timeout_count = 0U;
}

PlatformGpioId Sx1281Bus_NssGet(uint8_t instance)
{
    ProjectSx1281Resources resources;

    return (Sx1281Bus_ResourcesGet(instance, &resources) != 0U) ?
        resources.nss : (PlatformGpioId)PLATFORM_GPIO_COUNT;
}

PlatformGpioId Sx1281Bus_ResetGet(uint8_t instance)
{
    ProjectSx1281Resources resources;

    return (Sx1281Bus_ResourcesGet(instance, &resources) != 0U) ?
        resources.reset : (PlatformGpioId)PLATFORM_GPIO_COUNT;
}

PlatformGpioId Sx1281Bus_BusyGet(uint8_t instance)
{
    ProjectSx1281Resources resources;

    return (Sx1281Bus_ResourcesGet(instance, &resources) != 0U) ?
        resources.busy : (PlatformGpioId)PLATFORM_GPIO_COUNT;
}

PlatformGpioId Sx1281Bus_Dio1Get(uint8_t instance)
{
    ProjectSx1281Resources resources;

    return (Sx1281Bus_ResourcesGet(instance, &resources) != 0U) ?
        resources.dio1 : (PlatformGpioId)PLATFORM_GPIO_COUNT;
}

void GpioWrite(uint8_t instance, PlatformGpioId id, uint32_t value)
{
    (void)instance;
    (void)PlatformGpio_Write(id, (uint8_t)(value != 0U));
}

uint8_t GpioRead(uint8_t instance, PlatformGpioId id)
{
    uint8_t value = 0U;

    (void)instance;
    (void)PlatformGpio_Read(id, &value);
    return value;
}

void SpiIn(uint8_t instance, const uint8_t *tx_buffer, uint16_t size)
{
    ProjectSx1281Resources resources;
    PlatformResult result;

    SILVERSTAR_ASSERT(tx_buffer != NULL,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(size > 0U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if ((instance >= PROJECT_SX1281_INSTANCE_COUNT) ||
        (Sx1281Bus_ResourcesGet(instance, &resources) == 0U))
    {
        return;
    }
    result = PlatformSpi_Write(resources.spi, tx_buffer, size,
                               LORA_SPI_TIMEOUT_MS);

    if (result == PLATFORM_TIMEOUT)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_TIMEOUT;
        s_bus_status[instance].spi_timeout_count++;
    }
    else if (result != PLATFORM_OK)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_ERROR;
        s_bus_status[instance].spi_error_count++;
    }
    else
    {
        s_bus_status[instance].last_result = SX1281_BUS_OK;
    }
}

void SpiInOut(uint8_t instance, const uint8_t *tx_buffer,
              uint8_t *rx_buffer, uint16_t size)
{
    ProjectSx1281Resources resources;
    PlatformResult result;

    SILVERSTAR_ASSERT(tx_buffer != NULL,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(rx_buffer != NULL,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(size > 0U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if ((instance >= PROJECT_SX1281_INSTANCE_COUNT) ||
        (Sx1281Bus_ResourcesGet(instance, &resources) == 0U))
    {
        return;
    }
    result = PlatformSpi_Transfer(resources.spi, tx_buffer, rx_buffer, size,
                                  LORA_SPI_TIMEOUT_MS);

    if (result == PLATFORM_TIMEOUT)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_TIMEOUT;
        s_bus_status[instance].spi_timeout_count++;
    }
    else if (result != PLATFORM_OK)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_ERROR;
        s_bus_status[instance].spi_error_count++;
    }
    else
    {
        s_bus_status[instance].last_result = SX1281_BUS_OK;
    }
}

uint8_t GpioWaitLow(
    uint8_t instance, PlatformGpioId id, uint32_t timeout_ms)
{
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t guard;

    SILVERSTAR_ASSERT(id < PLATFORM_GPIO_COUNT,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(timeout_ms > 0U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    for (guard = 0U; guard < SX1281_BUSY_POLL_GUARD; guard++)
    {
        if (GpioRead(instance, id) == 0U)
        {
            s_bus_status[instance].last_result = SX1281_BUS_OK;
            return 1U;
        }
        if ((PlatformTime_Ms() - start_ms) >= timeout_ms)
        {
            s_bus_status[instance].last_result = SX1281_BUS_BUSY_TIMEOUT;
            s_bus_status[instance].busy_timeout_count++;
            return 0U;
        }
    }
    s_bus_status[instance].last_result = SX1281_BUS_BUSY_TIMEOUT;
    s_bus_status[instance].busy_timeout_count++;
    return 0U;
}

void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{
    if ((status != NULL) && (instance < PROJECT_SX1281_INSTANCE_COUNT))
    {
        *status = s_bus_status[instance];
    }
}
