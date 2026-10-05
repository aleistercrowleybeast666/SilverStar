#include "bmp390_adapter.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "system_version.h"

#define BMP390_BUS_TIMEOUT_MS 2U
#define BMP390_MAX_BURST_BYTES 24U
#define BMP390_FIXED_RATE_HZ 20U
#define BMP390_STALE_US 200000ULL

static Bmp390BusResult Bmp390Adapter_Read(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length)
{
    Bmp390Adapter *adapter = (Bmp390Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[BMP390_MAX_BURST_BYTES + 2U] = {0U};
    uint8_t rx[BMP390_MAX_BURST_BYTES + 2U];
    if ((adapter == NULL) || (bytes == NULL) ||
        (length == 0U) || (length > BMP390_MAX_BURST_BYTES))
    { return Bmp390BusError; }
    if (adapter->interface == Bmp390InterfaceI2c)
    {
        result = PlatformI2c_MemoryRead(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, bytes, length,
            BMP390_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Bmp390BusOk : Bmp390BusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Bmp390BusError; }
    tx[0] = register_address | 0x80U;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx,
        (uint16_t)length + 2U, BMP390_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    { return Bmp390BusError; }
    (void)memcpy(bytes, &rx[2], length);
    return Bmp390BusOk;
}

static Bmp390BusResult Bmp390Adapter_Write(void *bus,
    uint8_t register_address, uint8_t value)
{
    Bmp390Adapter *adapter = (Bmp390Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[2];
    uint8_t rx[2];
    if (adapter == NULL) { return Bmp390BusError; }
    if (adapter->interface == Bmp390InterfaceI2c)
    {
        result = PlatformI2c_MemoryWrite(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, &value, 1U,
            BMP390_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Bmp390BusOk : Bmp390BusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Bmp390BusError; }
    tx[0] = register_address & 0x7FU;
    tx[1] = value;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx, 2U,
        BMP390_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    return ((result == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        Bmp390BusOk : Bmp390BusError;
}

static SystemDeviceResult Bmp390Adapter_Init(Bmp390Adapter *adapter)
{
    Bmp390Port port;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    port.bus = adapter;
    port.read = Bmp390Adapter_Read;
    port.write = Bmp390Adapter_Write;
    Bmp390_Init(&adapter->core, &port);
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_InitI2c(Bmp390Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit)
{
    if ((adapter == NULL) || (i2c >= PLATFORM_I2C_COUNT) ||
        ((address_7bit != 0x76U) && (address_7bit != 0x77U)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Bmp390InterfaceI2c;
    adapter->i2c = i2c;
    adapter->address_7bit = address_7bit;
    return Bmp390Adapter_Init(adapter);
}

SystemDeviceResult Bmp390Adapter_InitSpi(Bmp390Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs)
{
    if ((adapter == NULL) || (spi >= PLATFORM_SPI_COUNT) ||
        (cs >= PLATFORM_GPIO_COUNT))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Bmp390InterfaceSpi;
    adapter->spi = spi;
    adapter->cs = cs;
    if (PlatformGpio_Write(cs, 1U) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    return Bmp390Adapter_Init(adapter);
}

SystemDeviceResult Bmp390Adapter_Start(Bmp390Adapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_Stop(Bmp390Adapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_Process(Bmp390Adapter *adapter)
{
    Bmp390StepResult result;
    if ((adapter == NULL) || (adapter->health.started == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    result = Bmp390_Step(&adapter->core, PlatformTime_Us());
    adapter->health.error_count = adapter->core.error_count;
    if (result == Bmp390StepSampleReady)
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
    if (result == Bmp390StepPending) { return SYSTEM_DEVICE_NOT_READY; }
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    if (result == Bmp390StepConversionTimeout)
    { adapter->health.timeout_count++; return SYSTEM_DEVICE_TIMEOUT; }
    return result == Bmp390StepNotPresent ?
        SYSTEM_DEVICE_NOT_PRESENT : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult Bmp390Adapter_InfoGet(const Bmp390Adapter *adapter,
    SystemDeviceInfo *info)
{
    if ((adapter == NULL) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "BMP390";
    info->model_name = "BMP390";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_BARO_VALID_PRESSURE;
    info->configuration_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_CapabilitiesGet(
    const Bmp390Adapter *adapter, uint32_t *mask)
{
    if ((adapter == NULL) || (mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_HealthGet(const Bmp390Adapter *adapter,
    SystemDeviceHealth *health)
{
    if ((adapter == NULL) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = adapter->health;
    if ((health->online != 0U) &&
        (PlatformTime_Us() >= health->last_receive_timestamp_us) &&
        ((PlatformTime_Us() - health->last_receive_timestamp_us) >
            BMP390_STALE_US))
    { health->healthy = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_LatestSampleGet(
    const Bmp390Adapter *adapter, SystemBarometerSample *sample)
{
    if ((adapter == NULL) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = adapter->core.sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_SelfTestRun(
    const Bmp390Adapter *adapter, SystemDeviceSelfTestResult *result)
{
    if ((adapter == NULL) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Bmp390Adapter_ConfigCheck(
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
            (config->output_rate_hz != BMP390_FIXED_RATE_HZ)))
    {
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_ConfigApply(Bmp390Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Bmp390Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    report->delegated_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Bmp390Adapter_ConfigVerify(const Bmp390Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Bmp390Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    report->matched_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_EffectiveConfigGet(
    const Bmp390Adapter *adapter, SystemBarometerConfig *config)
{
    if ((adapter == NULL) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    config->output_rate_hz = BMP390_FIXED_RATE_HZ;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp390Adapter_NoiseCharacteristicsGet(
    const Bmp390Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise)
{
    if ((adapter == NULL) || (noise == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
