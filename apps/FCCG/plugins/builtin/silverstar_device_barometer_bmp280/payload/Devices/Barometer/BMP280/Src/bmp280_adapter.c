#include "bmp280_adapter.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "system_version.h"

#define BMP280_BUS_TIMEOUT_MS 2U
#define BMP280_MAX_BURST_BYTES 24U
#define BMP280_FIXED_RATE_HZ 20U
#define BMP280_STALE_US 200000ULL

static Bmp280BusResult Bmp280Adapter_Read(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length)
{
    Bmp280Adapter *adapter = (Bmp280Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[BMP280_MAX_BURST_BYTES + 1U] = {0U};
    uint8_t rx[BMP280_MAX_BURST_BYTES + 1U];
    if ((adapter == NULL) || (bytes == NULL) ||
        (length == 0U) || (length > BMP280_MAX_BURST_BYTES))
    { return Bmp280BusError; }
    if (adapter->interface == Bmp280InterfaceI2c)
    {
        result = PlatformI2c_MemoryRead(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, bytes, length,
            BMP280_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Bmp280BusOk : Bmp280BusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Bmp280BusError; }
    tx[0] = register_address | 0x80U;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx,
        (uint16_t)length + 1U, BMP280_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    { return Bmp280BusError; }
    (void)memcpy(bytes, &rx[1], length);
    return Bmp280BusOk;
}

static Bmp280BusResult Bmp280Adapter_Write(void *bus,
    uint8_t register_address, uint8_t value)
{
    Bmp280Adapter *adapter = (Bmp280Adapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[2];
    uint8_t rx[2];
    if (adapter == NULL) { return Bmp280BusError; }
    if (adapter->interface == Bmp280InterfaceI2c)
    {
        result = PlatformI2c_MemoryWrite(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, &value, 1U,
            BMP280_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Bmp280BusOk : Bmp280BusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Bmp280BusError; }
    tx[0] = register_address & 0x7FU;
    tx[1] = value;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx, 2U,
        BMP280_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    return ((result == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        Bmp280BusOk : Bmp280BusError;
}

static SystemDeviceResult Bmp280Adapter_Init(Bmp280Adapter *adapter)
{
    Bmp280Port port;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    port.bus = adapter;
    port.read = Bmp280Adapter_Read;
    port.write = Bmp280Adapter_Write;
    Bmp280_Init(&adapter->core, &port);
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_InitI2c(Bmp280Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit)
{
    if ((adapter == NULL) || (i2c >= PLATFORM_I2C_COUNT) ||
        ((address_7bit != 0x76U) && (address_7bit != 0x77U)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Bmp280InterfaceI2c;
    adapter->i2c = i2c;
    adapter->address_7bit = address_7bit;
    return Bmp280Adapter_Init(adapter);
}

SystemDeviceResult Bmp280Adapter_InitSpi(Bmp280Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs)
{
    if ((adapter == NULL) || (spi >= PLATFORM_SPI_COUNT) ||
        (cs >= PLATFORM_GPIO_COUNT))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Bmp280InterfaceSpi;
    adapter->spi = spi;
    adapter->cs = cs;
    if (PlatformGpio_Write(cs, 1U) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    return Bmp280Adapter_Init(adapter);
}

SystemDeviceResult Bmp280Adapter_Start(Bmp280Adapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_Stop(Bmp280Adapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_Process(Bmp280Adapter *adapter)
{
    Bmp280StepResult result;
    if ((adapter == NULL) || (adapter->health.started == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    result = Bmp280_Step(&adapter->core, PlatformTime_Us());
    adapter->health.error_count = adapter->core.error_count;
    if (result == Bmp280StepSampleReady)
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
    if (result == Bmp280StepPending) { return SYSTEM_DEVICE_NOT_READY; }
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    if (result == Bmp280StepConversionTimeout)
    { adapter->health.timeout_count++; return SYSTEM_DEVICE_TIMEOUT; }
    return result == Bmp280StepNotPresent ?
        SYSTEM_DEVICE_NOT_PRESENT : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult Bmp280Adapter_InfoGet(const Bmp280Adapter *adapter,
    SystemDeviceInfo *info)
{
    if ((adapter == NULL) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "BMP280";
    info->model_name = "BMP280";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_BARO_VALID_PRESSURE;
    info->configuration_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_CapabilitiesGet(
    const Bmp280Adapter *adapter, uint32_t *mask)
{
    if ((adapter == NULL) || (mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_HealthGet(const Bmp280Adapter *adapter,
    SystemDeviceHealth *health)
{
    if ((adapter == NULL) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = adapter->health;
    if ((health->online != 0U) &&
        (PlatformTime_Us() >= health->last_receive_timestamp_us) &&
        ((PlatformTime_Us() - health->last_receive_timestamp_us) >
            BMP280_STALE_US))
    { health->healthy = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_LatestSampleGet(
    const Bmp280Adapter *adapter, SystemBarometerSample *sample)
{
    if ((adapter == NULL) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = adapter->core.sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_SelfTestRun(
    const Bmp280Adapter *adapter, SystemDeviceSelfTestResult *result)
{
    if ((adapter == NULL) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Bmp280Adapter_ConfigCheck(
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
            (config->output_rate_hz != BMP280_FIXED_RATE_HZ)))
    {
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_ConfigApply(Bmp280Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Bmp280Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    report->delegated_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Bmp280Adapter_ConfigVerify(const Bmp280Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Bmp280Adapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    report->matched_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_EffectiveConfigGet(
    const Bmp280Adapter *adapter, SystemBarometerConfig *config)
{
    if ((adapter == NULL) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    config->output_rate_hz = BMP280_FIXED_RATE_HZ;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Bmp280Adapter_NoiseCharacteristicsGet(
    const Bmp280Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise)
{
    if ((adapter == NULL) || (noise == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
