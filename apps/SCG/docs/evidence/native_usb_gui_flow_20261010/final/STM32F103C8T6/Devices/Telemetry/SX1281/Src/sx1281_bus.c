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

/* The first failed operation is retained until the next explicit bus init.
 * A BUSY wait may precede the SPI command, so its opcode is unknown. */
static void Sx1281Bus_FirstFailureRecord(uint8_t instance,
    Sx1281BusResult result, PlatformResult platform_result,
    uint8_t platform_result_valid, uint8_t opcode, uint8_t opcode_valid,
    uint16_t length, uint32_t started_ms,
    const PlatformSpiDriverObservation *observation)
{
    Sx1281BusStatus *status = &s_bus_status[instance];
    if (status->first_failure_valid != 0U) { return; }
    status->first_failure_at_ms = PlatformTime_Ms();
    status->first_failure_elapsed_ms = status->first_failure_at_ms - started_ms;
    status->first_failure_platform_result = platform_result;
    status->first_failure_result = result;
    status->first_failure_length = length;
    status->first_failure_opcode = opcode;
    status->first_failure_opcode_valid = opcode_valid;
    status->first_failure_platform_result_valid = platform_result_valid;
    if ((observation != NULL) && (observation->valid != 0U))
    {
        status->first_failure_driver_status = observation->driver_status;
        status->first_failure_driver_error_code = observation->driver_error_code;
        status->first_failure_driver_state = observation->driver_state;
        status->first_failure_spi_sr = observation->spi_sr;
        status->first_failure_driver_elapsed_ms = observation->driver_elapsed_ms;
        status->first_failure_tx_remaining = observation->tx_remaining;
        status->first_failure_rx_remaining = observation->rx_remaining;
        status->first_failure_driver_valid = 1U;
    }
    status->first_failure_valid = 1U;
}

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
    s_bus_status[instance].first_failure_valid = 0U;
    s_bus_status[instance].first_failure_opcode_valid = 0U;
    s_bus_status[instance].first_failure_platform_result_valid = 0U;
    s_bus_status[instance].first_failure_driver_valid = 0U;
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
    PlatformSpiDriverObservation observation = {0};
    uint32_t started_ms;

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
    started_ms = PlatformTime_Ms();
    result = PlatformSpi_WriteObserved(resources.spi, tx_buffer, size,
        LORA_SPI_TIMEOUT_MS, &observation);

    if (result == PLATFORM_TIMEOUT)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_TIMEOUT;
        s_bus_status[instance].spi_timeout_count++;
        Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_SPI_TIMEOUT,
            result, 1U, tx_buffer[0], 1U, size, started_ms, &observation);
    }
    else if (result != PLATFORM_OK)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_ERROR;
        s_bus_status[instance].spi_error_count++;
        Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_SPI_ERROR,
            result, 1U, tx_buffer[0], 1U, size, started_ms, &observation);
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
    PlatformSpiDriverObservation observation = {0};
    uint32_t started_ms;

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
    started_ms = PlatformTime_Ms();
    result = PlatformSpi_TransferObserved(resources.spi, tx_buffer, rx_buffer,
        size, LORA_SPI_TIMEOUT_MS, &observation);

    if (result == PLATFORM_TIMEOUT)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_TIMEOUT;
        s_bus_status[instance].spi_timeout_count++;
        Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_SPI_TIMEOUT,
            result, 1U, tx_buffer[0], 1U, size, started_ms, &observation);
    }
    else if (result != PLATFORM_OK)
    {
        s_bus_status[instance].last_result = SX1281_BUS_SPI_ERROR;
        s_bus_status[instance].spi_error_count++;
        Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_SPI_ERROR,
            result, 1U, tx_buffer[0], 1U, size, started_ms, &observation);
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
            Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_BUSY_TIMEOUT,
                PLATFORM_OK, 0U, 0U, 0U, 0U, start_ms, NULL);
            return 0U;
        }
    }
    s_bus_status[instance].last_result = SX1281_BUS_BUSY_TIMEOUT;
    s_bus_status[instance].busy_timeout_count++;
    Sx1281Bus_FirstFailureRecord(instance, SX1281_BUS_BUSY_TIMEOUT,
        PLATFORM_OK, 0U, 0U, 0U, 0U, start_ms, NULL);
    return 0U;
}

void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{
    if ((status != NULL) && (instance < PROJECT_SX1281_INSTANCE_COUNT))
    {
        *status = s_bus_status[instance];
    }
}
