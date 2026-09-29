#include "lis3mdl_adapter.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "system_version.h"

#define LIS3MDL_BUS_TIMEOUT_MS 2U
#define LIS3MDL_MAX_BURST_BYTES 8U
#define LIS3MDL_FIXED_RATE_HZ 20U
#define LIS3MDL_STALE_US 200000ULL

static Lis3mdlBusResult Lis3mdlAdapter_Read(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length)
{
    Lis3mdlAdapter *adapter = (Lis3mdlAdapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[LIS3MDL_MAX_BURST_BYTES + 1U] = {0U};
    uint8_t rx[LIS3MDL_MAX_BURST_BYTES + 1U];
    if ((adapter == NULL) || (bytes == NULL) ||
        (length == 0U) || (length > LIS3MDL_MAX_BURST_BYTES))
    { return Lis3mdlBusError; }
    if (adapter->interface == Lis3mdlInterfaceI2c)
    {
        result = PlatformI2c_MemoryRead(adapter->i2c,
            adapter->address_7bit,
            (uint16_t)(register_address | (length > 1U ? 0x80U : 0U)),
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, bytes, length,
            LIS3MDL_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Lis3mdlBusOk : Lis3mdlBusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Lis3mdlBusError; }
    tx[0] = register_address | 0x80U | (length > 1U ? 0x40U : 0U);
    result = PlatformSpi_Transfer(adapter->spi, tx, rx,
        (uint16_t)length + 1U, LIS3MDL_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    { return Lis3mdlBusError; }
    (void)memcpy(bytes, &rx[1], length);
    return Lis3mdlBusOk;
}

static Lis3mdlBusResult Lis3mdlAdapter_Write(void *bus,
    uint8_t register_address, uint8_t value)
{
    Lis3mdlAdapter *adapter = (Lis3mdlAdapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[2];
    uint8_t rx[2];
    if (adapter == NULL) { return Lis3mdlBusError; }
    if (adapter->interface == Lis3mdlInterfaceI2c)
    {
        result = PlatformI2c_MemoryWrite(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, &value, 1U,
            LIS3MDL_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Lis3mdlBusOk : Lis3mdlBusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Lis3mdlBusError; }
    tx[0] = register_address & 0x7FU;
    tx[1] = value;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx, 2U,
        LIS3MDL_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    return ((result == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        Lis3mdlBusOk : Lis3mdlBusError;
}

static SystemDeviceResult Lis3mdlAdapter_Init(Lis3mdlAdapter *adapter)
{
    Lis3mdlPort port;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    port.bus = adapter;
    port.read = Lis3mdlAdapter_Read;
    port.write = Lis3mdlAdapter_Write;
    Lis3mdl_Init(&adapter->core, &port);
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_InitI2c(Lis3mdlAdapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit)
{
    if ((adapter == NULL) || (i2c >= PLATFORM_I2C_COUNT) ||
        ((address_7bit != 0x1CU) && (address_7bit != 0x1EU)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Lis3mdlInterfaceI2c;
    adapter->i2c = i2c;
    adapter->address_7bit = address_7bit;
    return Lis3mdlAdapter_Init(adapter);
}

SystemDeviceResult Lis3mdlAdapter_InitSpi(Lis3mdlAdapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs)
{
    if ((adapter == NULL) || (spi >= PLATFORM_SPI_COUNT) ||
        (cs >= PLATFORM_GPIO_COUNT))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Lis3mdlInterfaceSpi;
    adapter->spi = spi;
    adapter->cs = cs;
    if (PlatformGpio_Write(cs, 1U) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    return Lis3mdlAdapter_Init(adapter);
}

SystemDeviceResult Lis3mdlAdapter_Start(Lis3mdlAdapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_Stop(Lis3mdlAdapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_Process(Lis3mdlAdapter *adapter)
{
    Lis3mdlStepResult result;
    if ((adapter == NULL) || (adapter->health.started == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    result = Lis3mdl_Step(&adapter->core, PlatformTime_Us());
    adapter->health.error_count = adapter->core.error_count;
    if (result == Lis3mdlStepSampleReady)
    {
        adapter->health.sample_count = adapter->core.sequence;
        adapter->health.last_sample_timestamp_us =
            adapter->core.sample.sample_timestamp_us;
        adapter->health.last_receive_timestamp_us =
            adapter->core.sample.receive_timestamp_us;
        adapter->health.online = 1U;
        adapter->health.healthy = 1U;
        return SYSTEM_DEVICE_OK;
    }
    if (result == Lis3mdlStepPending) { return SYSTEM_DEVICE_NOT_READY; }
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    if (result == Lis3mdlStepNotPresent) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return result == Lis3mdlStepVerifyFailed ?
        SYSTEM_DEVICE_VERIFY_FAILED : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult Lis3mdlAdapter_InfoGet(const Lis3mdlAdapter *adapter,
    SystemDeviceInfo *info)
{
    if ((adapter == NULL) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "LIS3MDL";
    info->model_name = "LIS3MDL";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_MAG_CAP_RAW_OUTPUT |
        SYSTEM_MAG_CAP_PHYSICAL_UNIT | SYSTEM_MAG_CAP_TEMPERATURE |
        SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE | SYSTEM_MAG_CAP_CONFIG_RANGE;
    info->configuration_mask = SYSTEM_MAG_CFG_OUTPUT_RATE |
        SYSTEM_MAG_CFG_RANGE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_CapabilitiesGet(
    const Lis3mdlAdapter *adapter, uint32_t *mask)
{
    if ((adapter == NULL) || (mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_MAG_CAP_RAW_OUTPUT | SYSTEM_MAG_CAP_PHYSICAL_UNIT |
        SYSTEM_MAG_CAP_TEMPERATURE | SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE |
        SYSTEM_MAG_CAP_CONFIG_RANGE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_HealthGet(const Lis3mdlAdapter *adapter,
    SystemDeviceHealth *health)
{
    if ((adapter == NULL) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = adapter->health;
    uint64_t now_us = PlatformTime_Us();
    if ((health->online != 0U) &&
        (now_us >= health->last_receive_timestamp_us) &&
        ((now_us - health->last_receive_timestamp_us) > LIS3MDL_STALE_US))
    { health->healthy = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_LatestSampleGet(
    const Lis3mdlAdapter *adapter, SystemMagnetometerSample *sample)
{
    if ((adapter == NULL) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = adapter->core.sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_SelfTestRun(
    const Lis3mdlAdapter *adapter, SystemDeviceSelfTestResult *result)
{
    if ((adapter == NULL) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Lis3mdlAdapter_ConfigCheck(
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = SYSTEM_MAG_CFG_OUTPUT_RATE |
        SYSTEM_MAG_CFG_RANGE;
    if (((config->required_mask & ~report->supported_mask) != 0U) ||
        (((config->requested_mask & SYSTEM_MAG_CFG_OUTPUT_RATE) != 0U) &&
            (config->output_rate_hz != LIS3MDL_FIXED_RATE_HZ)) ||
        (((config->requested_mask & SYSTEM_MAG_CFG_RANGE) != 0U) &&
            (config->range_uT != 400.0F)))
    {
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_ConfigApply(Lis3mdlAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Lis3mdlAdapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    report->delegated_mask = config->requested_mask &
        (SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE);
    report->success = 1U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Lis3mdlAdapter_ConfigVerify(const Lis3mdlAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Lis3mdlAdapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    report->matched_mask = config->requested_mask &
        (SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE);
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lis3mdlAdapter_EffectiveConfigGet(
    const Lis3mdlAdapter *adapter, SystemMagnetometerConfig *config)
{
    if ((adapter == NULL) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE;
    config->output_rate_hz = LIS3MDL_FIXED_RATE_HZ;
    config->range_uT = 400.0F;
    return SYSTEM_DEVICE_OK;
}
