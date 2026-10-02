#include "ms5611_adapter.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "system_version.h"

#define MS5611_BUS_TIMEOUT_MS 2U
#define MS5611_MAX_READ_BYTES 3U
#define MS5611_FIXED_RATE_HZ 20U
#define MS5611_STALE_US 200000ULL

Ms5611BusResult Ms5611Bus_Write(void *bus,
    uint8_t command)
{
    Ms5611Adapter *adapter = (Ms5611Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    if (adapter == NULL) { return Ms5611BusError; }
    if (adapter->interface == Ms5611InterfaceI2c)
    {
        if (SYSTEM_BUILD_MS5611_I2C_ENABLED == 0U) { return Ms5611BusError; }
        result = PlatformI2c_Write(adapter->i2c, adapter->address_7bit,
            &command, 1U, MS5611_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Ms5611BusOk : Ms5611BusError;
    }
    if ((adapter->interface != Ms5611InterfaceSpi) ||
        (SYSTEM_BUILD_MS5611_SPI_ENABLED == 0U)) { return Ms5611BusError; }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Ms5611BusError; }
    result = PlatformSpi_Write(adapter->spi, &command, 1U,
        MS5611_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    return ((result == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        Ms5611BusOk : Ms5611BusError;
}

Ms5611BusResult Ms5611Bus_Read(void *bus,
    uint8_t command, uint8_t *bytes, uint8_t length)
{
    Ms5611Adapter *adapter = (Ms5611Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[MS5611_MAX_READ_BYTES + 1U] = {0U};
    uint8_t rx[MS5611_MAX_READ_BYTES + 1U];
    if ((adapter == NULL) || (bytes == NULL) ||
        (length == 0U) || (length > MS5611_MAX_READ_BYTES))
    { return Ms5611BusError; }
    if (adapter->interface == Ms5611InterfaceI2c)
    {
        if (SYSTEM_BUILD_MS5611_I2C_ENABLED == 0U) { return Ms5611BusError; }
        result = PlatformI2c_MemoryRead(adapter->i2c,
            adapter->address_7bit, command,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, bytes, length,
            MS5611_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Ms5611BusOk : Ms5611BusError;
    }
    if ((adapter->interface != Ms5611InterfaceSpi) ||
        (SYSTEM_BUILD_MS5611_SPI_ENABLED == 0U)) { return Ms5611BusError; }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Ms5611BusError; }
    tx[0] = command;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx,
        (uint16_t)length + 1U, MS5611_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    { return Ms5611BusError; }
    (void)memcpy(bytes, &rx[1], length);
    return Ms5611BusOk;
}

static SystemDeviceResult Ms5611Adapter_Init(Ms5611Adapter *adapter)
{
    Ms5611Port port;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    port.bus = adapter;
    Ms5611_Init(&adapter->core, &port);
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_InitI2c(Ms5611Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit)
{
    if ((SYSTEM_BUILD_MS5611_I2C_ENABLED == 0U) || (adapter == NULL) || (i2c >= PLATFORM_I2C_COUNT) ||
        ((address_7bit != 0x76U) && (address_7bit != 0x77U)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Ms5611InterfaceI2c;
    adapter->i2c = i2c;
    adapter->address_7bit = address_7bit;
    return Ms5611Adapter_Init(adapter);
}

SystemDeviceResult Ms5611Adapter_InitSpi(Ms5611Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs)
{
    if ((SYSTEM_BUILD_MS5611_SPI_ENABLED == 0U) || (adapter == NULL) || (spi >= PLATFORM_SPI_COUNT) ||
        (cs >= PLATFORM_GPIO_COUNT))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Ms5611InterfaceSpi;
    adapter->spi = spi;
    adapter->cs = cs;
    if (PlatformGpio_Write(cs, 1U) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    return Ms5611Adapter_Init(adapter);
}

SystemDeviceResult Ms5611Adapter_Start(Ms5611Adapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_Stop(Ms5611Adapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_Process(Ms5611Adapter *adapter)
{
    Ms5611StepResult result;
    if ((adapter == NULL) || (adapter->health.started == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    result = Ms5611_Step(&adapter->core, PlatformTime_Us());
    adapter->health.error_count = adapter->core.error_count;
    if (result == Ms5611StepSampleReady)
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
    if (result == Ms5611StepPending) { return SYSTEM_DEVICE_NOT_READY; }
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    if (result == Ms5611StepConversionTimeout)
    { adapter->health.timeout_count++; return SYSTEM_DEVICE_TIMEOUT; }
    return result == Ms5611StepPromCrcError ?
        SYSTEM_DEVICE_VERIFY_FAILED : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult Ms5611Adapter_InfoGet(const Ms5611Adapter *adapter,
    SystemDeviceInfo *info)
{
    if ((adapter == NULL) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "MS5611";
    info->model_name = "MS5611-01BA03";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_BARO_VALID_PRESSURE;
    info->configuration_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_CapabilitiesGet(
    const Ms5611Adapter *adapter, uint32_t *mask)
{
    if ((adapter == NULL) || (mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_HealthGet(const Ms5611Adapter *adapter,
    SystemDeviceHealth *health)
{
    uint64_t now_us;
    if ((adapter == NULL) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = adapter->health;
    now_us = PlatformTime_Us();
    if ((health->online != 0U) &&
        (now_us >= health->last_receive_timestamp_us) &&
        ((now_us - health->last_receive_timestamp_us) > MS5611_STALE_US))
    { health->healthy = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_LatestSampleGet(
    const Ms5611Adapter *adapter, SystemBarometerSample *sample)
{
    if ((adapter == NULL) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = adapter->core.sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_SelfTestRun(
    const Ms5611Adapter *adapter, SystemDeviceSelfTestResult *result)
{
    if ((adapter == NULL) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Ms5611Adapter_ConfigCheck(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    if (((config->required_mask & ~SYSTEM_BARO_CFG_OUTPUT_RATE) != 0U) ||
        (((config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE) != 0U) &&
            (config->output_rate_hz != MS5611_FIXED_RATE_HZ)))
    {
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_ConfigApply(Ms5611Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Ms5611Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    report->delegated_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Ms5611Adapter_ConfigVerify(const Ms5611Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Ms5611Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    report->matched_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_EffectiveConfigGet(
    const Ms5611Adapter *adapter, SystemBarometerConfig *config)
{
    if ((adapter == NULL) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    config->output_rate_hz = MS5611_FIXED_RATE_HZ;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Ms5611Adapter_NoiseCharacteristicsGet(
    const Ms5611Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise)
{
    if ((adapter == NULL) || (noise == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
