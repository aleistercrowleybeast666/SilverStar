#include "mmc5983ma_adapter.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "system_version.h"

#define MMC5983MA_BUS_TIMEOUT_MS 2U
#define MMC5983MA_MAX_BURST_BYTES 7U
#define MMC5983MA_FIXED_RATE_HZ 20U
#define MMC5983MA_STALE_US 200000ULL

static Mmc5983maBusResult Mmc5983maAdapter_Read(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length)
{
    Mmc5983maAdapter *adapter = (Mmc5983maAdapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[MMC5983MA_MAX_BURST_BYTES + 1U] = {0U};
    uint8_t rx[MMC5983MA_MAX_BURST_BYTES + 1U];
    if ((adapter == NULL) || (bytes == NULL) ||
        (length == 0U) || (length > MMC5983MA_MAX_BURST_BYTES))
    { return Mmc5983maBusError; }
    if (adapter->interface == Mmc5983maInterfaceI2c)
    {
        result = PlatformI2c_MemoryRead(adapter->i2c,
            adapter->address_7bit,
            register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, bytes, length,
            MMC5983MA_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Mmc5983maBusOk : Mmc5983maBusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Mmc5983maBusError; }
    tx[0] = register_address | 0x80U;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx,
        (uint16_t)length + 1U, MMC5983MA_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    { return Mmc5983maBusError; }
    (void)memcpy(bytes, &rx[1], length);
    return Mmc5983maBusOk;
}

static Mmc5983maBusResult Mmc5983maAdapter_Write(void *bus,
    uint8_t register_address, uint8_t value)
{
    Mmc5983maAdapter *adapter = (Mmc5983maAdapter *)bus;
    PlatformResult result;
    PlatformResult release;
    uint8_t tx[2];
    uint8_t rx[2];
    if (adapter == NULL) { return Mmc5983maBusError; }
    if (adapter->interface == Mmc5983maInterfaceI2c)
    {
        result = PlatformI2c_MemoryWrite(adapter->i2c,
            adapter->address_7bit, register_address,
            PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, &value, 1U,
            MMC5983MA_BUS_TIMEOUT_MS);
        return result == PLATFORM_OK ? Mmc5983maBusOk : Mmc5983maBusError;
    }
    if (PlatformGpio_Write(adapter->cs, 0U) != PLATFORM_OK)
    { return Mmc5983maBusError; }
    tx[0] = register_address & 0x3FU;
    tx[1] = value;
    result = PlatformSpi_Transfer(adapter->spi, tx, rx, 2U,
        MMC5983MA_BUS_TIMEOUT_MS);
    release = PlatformGpio_Write(adapter->cs, 1U);
    return ((result == PLATFORM_OK) && (release == PLATFORM_OK)) ?
        Mmc5983maBusOk : Mmc5983maBusError;
}

static SystemDeviceResult Mmc5983maAdapter_Init(Mmc5983maAdapter *adapter)
{
    Mmc5983maPort port;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    port.bus = adapter;
    port.read = Mmc5983maAdapter_Read;
    port.write = Mmc5983maAdapter_Write;
    Mmc5983ma_Init(&adapter->core, &port);
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_InitI2c(Mmc5983maAdapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit)
{
    if ((adapter == NULL) || (i2c >= PLATFORM_I2C_COUNT) ||
        (address_7bit != 0x30U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Mmc5983maInterfaceI2c;
    adapter->i2c = i2c;
    adapter->address_7bit = address_7bit;
    return Mmc5983maAdapter_Init(adapter);
}

SystemDeviceResult Mmc5983maAdapter_InitSpi(Mmc5983maAdapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs)
{
    if ((adapter == NULL) || (spi >= PLATFORM_SPI_COUNT) ||
        (cs >= PLATFORM_GPIO_COUNT))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->interface = Mmc5983maInterfaceSpi;
    adapter->spi = spi;
    adapter->cs = cs;
    if (PlatformGpio_Write(cs, 1U) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    return Mmc5983maAdapter_Init(adapter);
}

SystemDeviceResult Mmc5983maAdapter_Start(Mmc5983maAdapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_Stop(Mmc5983maAdapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_Process(Mmc5983maAdapter *adapter)
{
    Mmc5983maStepResult result;
    if ((adapter == NULL) || (adapter->health.started == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    result = Mmc5983ma_Step(&adapter->core, PlatformTime_Us());
    adapter->health.error_count = adapter->core.error_count;
    if (result == Mmc5983maStepSampleReady)
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
    if (result == Mmc5983maStepPending) { return SYSTEM_DEVICE_NOT_READY; }
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    if (result == Mmc5983maStepNotPresent) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return result == Mmc5983maStepVerifyFailed ?
        SYSTEM_DEVICE_VERIFY_FAILED : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult Mmc5983maAdapter_InfoGet(const Mmc5983maAdapter *adapter,
    SystemDeviceInfo *info)
{
    if ((adapter == NULL) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "MMC5983MA";
    info->model_name = "MMC5983MA";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_MAG_CAP_RAW_OUTPUT |
        SYSTEM_MAG_CAP_PHYSICAL_UNIT | SYSTEM_MAG_CAP_TEMPERATURE |
        SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE | SYSTEM_MAG_CAP_CONFIG_RANGE;
    info->configuration_mask = SYSTEM_MAG_CFG_OUTPUT_RATE |
        SYSTEM_MAG_CFG_RANGE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_CapabilitiesGet(
    const Mmc5983maAdapter *adapter, uint32_t *mask)
{
    if ((adapter == NULL) || (mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_MAG_CAP_RAW_OUTPUT | SYSTEM_MAG_CAP_PHYSICAL_UNIT |
        SYSTEM_MAG_CAP_TEMPERATURE | SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE |
        SYSTEM_MAG_CAP_CONFIG_RANGE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_HealthGet(const Mmc5983maAdapter *adapter,
    SystemDeviceHealth *health)
{
    if ((adapter == NULL) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = adapter->health;
    uint64_t now_us = PlatformTime_Us();
    if ((health->online != 0U) &&
        (now_us >= health->last_receive_timestamp_us) &&
        ((now_us - health->last_receive_timestamp_us) > MMC5983MA_STALE_US))
    { health->healthy = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_LatestSampleGet(
    const Mmc5983maAdapter *adapter, SystemMagnetometerSample *sample)
{
    if ((adapter == NULL) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = adapter->core.sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_SelfTestRun(
    const Mmc5983maAdapter *adapter, SystemDeviceSelfTestResult *result)
{
    if ((adapter == NULL) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mmc5983maAdapter_ConfigCheck(
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
            (config->output_rate_hz != MMC5983MA_FIXED_RATE_HZ)) ||
        (((config->requested_mask & SYSTEM_MAG_CFG_RANGE) != 0U) &&
            (config->range_uT != 800.0F)))
    {
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_ConfigApply(Mmc5983maAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Mmc5983maAdapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    report->delegated_mask = config->requested_mask &
        (SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE);
    report->success = 1U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Mmc5983maAdapter_ConfigVerify(const Mmc5983maAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Mmc5983maAdapter_ConfigCheck(config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->core.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    report->matched_mask = config->requested_mask &
        (SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE);
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mmc5983maAdapter_EffectiveConfigGet(
    const Mmc5983maAdapter *adapter, SystemMagnetometerConfig *config)
{
    if ((adapter == NULL) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE;
    config->output_rate_hz = MMC5983MA_FIXED_RATE_HZ;
    config->range_uT = 800.0F;
    return SYSTEM_DEVICE_OK;
}
