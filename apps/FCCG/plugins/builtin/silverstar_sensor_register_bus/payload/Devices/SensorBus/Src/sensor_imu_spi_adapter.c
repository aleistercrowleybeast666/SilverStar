#include "sensor_imu_adapter.h"

#include <stddef.h>
#include <string.h>
#include "platform_time.h"
#include "silverstar_assert.h"

#define SENSOR_SPI_TRANSFER_MAX (SENSOR_REGISTER_TRANSFER_MAX + 2U)
#define SENSOR_SPI_TIMEOUT_MS 2U

static SensorBusResult SensorImuSpi_Transfer(SensorImuAdapter *adapter,
    uint16_t reg, const uint8_t *tx, uint8_t *rx, uint16_t length)
{
    PlatformGpioId cs = ((reg & 0x100U) != 0U) ?
        adapter->spi_resources.auxiliary_cs : adapter->spi_resources.cs;
    PlatformResult transfer;
    PlatformResult release;
    if (PlatformGpio_Write(cs, 0U) != PLATFORM_OK) { return SENSOR_BUS_IO_ERROR; }
    transfer = PlatformSpi_Transfer(adapter->spi_resources.spi, tx, rx, length, SENSOR_SPI_TIMEOUT_MS);
    /* Release CS even when the peripheral times out. Preserve either failure. */
    release = PlatformGpio_Write(cs, 1U);
    return ((transfer == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        SENSOR_BUS_OK : SENSOR_BUS_IO_ERROR;
}

static SensorBusResult SensorImuSpi_Read(void *context, uint16_t reg,
    uint8_t *data, uint16_t length, uint32_t timeout_us)
{
    SensorImuAdapter *adapter = context;
    uint8_t tx[SENSOR_SPI_TRANSFER_MAX] = {0U};
    uint8_t rx[SENSOR_SPI_TRANSFER_MAX];
    uint8_t dummy;
    SensorBusResult result;
    if ((adapter == NULL) || (data == NULL) || (length > SENSOR_REGISTER_TRANSFER_MAX) ||
        (timeout_us != SENSOR_REGISTER_TIMEOUT_US)) { return SENSOR_BUS_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    dummy = ((reg & 0x100U) != 0U) ? adapter->driver.profile->auxiliary_spi_dummy_bytes :
        adapter->driver.profile->spi_dummy_bytes;
    if (dummy > 1U) { return SENSOR_BUS_INVALID_ARGUMENT; }
    tx[0] = (uint8_t)(reg | 0x80U);
    result = SensorImuSpi_Transfer(adapter, reg, tx, rx, (uint16_t)(length + dummy + 1U));
    if (result == SENSOR_BUS_OK) { memcpy(data, &rx[1U + dummy], length); }
    return result;
}

static SensorBusResult SensorImuSpi_Write(void *context, uint16_t reg,
    const uint8_t *data, uint16_t length, uint32_t timeout_us)
{
    SensorImuAdapter *adapter = context;
    uint8_t tx[SENSOR_SPI_TRANSFER_MAX];
    uint8_t rx[SENSOR_SPI_TRANSFER_MAX];
    if ((adapter == NULL) || (data == NULL) || (length > SENSOR_REGISTER_TRANSFER_MAX) ||
        (timeout_us != SENSOR_REGISTER_TIMEOUT_US)) { return SENSOR_BUS_INVALID_ARGUMENT; }
    tx[0] = (uint8_t)(reg & 0x7FU);
    memcpy(&tx[1], data, length);
    return SensorImuSpi_Transfer(adapter, reg, tx, rx, (uint16_t)(length + 1U));
}

SystemDeviceResult SensorImuAdapter_InitSpi(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, const SensorImuSpiResources *resources,
    uint32_t source_id)
{
    SensorRegisterBus bus;
    if ((adapter == NULL) || (profile == NULL) || (resources == NULL) ||
        (resources->spi >= PLATFORM_SPI_COUNT) || (resources->cs >= PLATFORM_GPIO_COUNT) ||
        (resources->drdy >= PLATFORM_GPIO_COUNT) || (profile->spi_supported == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((profile->auxiliary_address_7bit != 0U) &&
        ((resources->auxiliary_cs >= PLATFORM_GPIO_COUNT) ||
         (resources->auxiliary_drdy >= PLATFORM_GPIO_COUNT) || (resources->auxiliary_cs == resources->cs)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(adapter, 0, sizeof(*adapter));
    adapter->spi_resources = *resources;
    if (PlatformGpio_Write(resources->cs, 1U) != PLATFORM_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    if ((profile->auxiliary_address_7bit != 0U) &&
        (PlatformGpio_Write(resources->auxiliary_cs, 1U) != PLATFORM_OK)) { return SYSTEM_DEVICE_IO_ERROR; }
    bus.context = adapter; bus.read = SensorImuSpi_Read; bus.write = SensorImuSpi_Write; bus.kind = SENSOR_BUS_SPI;
    if (SensorImu_Init(&adapter->driver, &bus, profile, source_id) != SENSOR_IMU_OK)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SensorImu_BeginConfigure(&adapter->driver, PlatformTime_Us(), 1U) != SENSOR_IMU_BUSY)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}
