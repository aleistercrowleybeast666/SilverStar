#include "sensor_imu_adapter.h"
#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>
#include "platform_time.h"
#include "platform_critical.h"

#define SENSOR_ADAPTER_BUS_TIMEOUT_MS 2U
#define SENSOR_ADAPTER_STALE_US 100000U

static SensorBusResult SensorImuAdapter_ReadRegister(void *context,
    uint16_t reg, uint8_t *data, uint16_t length, uint32_t timeout_us)
{
    SensorImuAdapter *adapter = context;
    PlatformResult result;
    uint8_t buffer[SENSOR_REGISTER_TRANSFER_MAX + 2U];
    uint8_t dummy;
    uint16_t address;
    if ((adapter == NULL) || (timeout_us != SENSOR_REGISTER_TIMEOUT_US))
    {
        return SENSOR_BUS_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((adapter->driver.profile == NULL) || (length > SENSOR_REGISTER_TRANSFER_MAX))
    {
        return SENSOR_BUS_INVALID_ARGUMENT;
    }
    dummy = adapter->driver.profile->i2c_dummy_bytes;
    if (dummy > 2U) { return SENSOR_BUS_INVALID_ARGUMENT; }
    address = ((reg & 0x100U) != 0U) ?
        adapter->driver.profile->auxiliary_address_7bit : adapter->address_7bit;
    result = PlatformI2c_MemoryRead(((reg & 0x100U) != 0U) ?
        adapter->auxiliary_bus_id : adapter->bus_id, address,
        reg & 0xFFU, PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, buffer, length + dummy,
        SENSOR_ADAPTER_BUS_TIMEOUT_MS);
    if (result == PLATFORM_OK) { memcpy(data, &buffer[dummy], length); }
    return (result == PLATFORM_OK) ? SENSOR_BUS_OK : SENSOR_BUS_IO_ERROR;
}

static SensorBusResult SensorImuAdapter_WriteRegister(void *context,
    uint16_t reg, const uint8_t *data, uint16_t length, uint32_t timeout_us)
{
    SensorImuAdapter *adapter = context;
    PlatformResult result;
    uint16_t address;
    if ((adapter == NULL) || (timeout_us != SENSOR_REGISTER_TIMEOUT_US))
    {
        return SENSOR_BUS_INVALID_ARGUMENT;
    }
    if (adapter->driver.profile == NULL) { return SENSOR_BUS_INVALID_ARGUMENT; }
    address = ((reg & 0x100U) != 0U) ?
        adapter->driver.profile->auxiliary_address_7bit : adapter->address_7bit;
    result = PlatformI2c_MemoryWrite(((reg & 0x100U) != 0U) ?
        adapter->auxiliary_bus_id : adapter->bus_id, address,
        reg & 0xFFU, PLATFORM_I2C_MEMORY_ADDRESS_8_BIT, data, length,
        SENSOR_ADAPTER_BUS_TIMEOUT_MS);
    return (result == PLATFORM_OK) ? SENSOR_BUS_OK : SENSOR_BUS_IO_ERROR;
}

SystemDeviceResult SensorImuAdapter_InitI2c(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, PlatformI2cId bus_id,
    PlatformI2cId auxiliary_bus_id, uint16_t address_7bit, uint32_t source_id)
{
    SensorRegisterBus bus;
    SensorImuResult result;
    if ((adapter == NULL) || (profile == NULL) ||
        (bus_id >= PLATFORM_I2C_COUNT) ||
        (auxiliary_bus_id >= PLATFORM_I2C_COUNT) ||
        (address_7bit < 8U) || (address_7bit > 119U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(adapter, 0, sizeof(*adapter));
    adapter->bus_id = bus_id;
    adapter->auxiliary_bus_id = auxiliary_bus_id;
    adapter->address_7bit = address_7bit;
    adapter->spi_resources.drdy = (PlatformGpioId)PLATFORM_GPIO_COUNT;
    adapter->spi_resources.auxiliary_drdy = (PlatformGpioId)PLATFORM_GPIO_COUNT;
    bus.context = adapter;
    bus.read = SensorImuAdapter_ReadRegister;
    bus.write = SensorImuAdapter_WriteRegister;
    bus.kind = SENSOR_BUS_I2C;
    result = SensorImu_Init(&adapter->driver, &bus, profile, source_id);
    if (result != SENSOR_IMU_OK) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = SensorImu_BeginConfigure(&adapter->driver, PlatformTime_Us(), 1U);
    if (result != SENSOR_IMU_BUSY) { return SYSTEM_DEVICE_VERIFY_FAILED; }
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_Start(SensorImuAdapter *adapter)
{
    if ((adapter == NULL) || (adapter->health.initialized == 0U))
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (adapter->driver.state == SENSOR_IMU_STOPPED)
    {
        if (SensorImu_Start(&adapter->driver, PlatformTime_Us()) != SENSOR_IMU_BUSY)
        {
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
    }
    adapter->started = 1U;
    adapter->health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_Stop(SensorImuAdapter *adapter)
{
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    adapter->started = 0U;
    adapter->health.started = 0U;
    adapter->health.healthy = 0U;
    return (SensorImu_Stop(&adapter->driver) == SENSOR_IMU_OK) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}

static void SensorImuAdapter_Publish(SensorImuAdapter *adapter,
    const SensorImuSample *native)
{
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t axis;
    PlatformCriticalState lock = PlatformCritical_Enter();
    adapter->latest.sample_timestamp_us = native->sample_timestamp_us;
    adapter->latest.receive_timestamp_us = native->receive_timestamp_us;
    adapter->latest.sequence = native->sequence;
    adapter->latest.temperature_c = native->temperature_c;
    adapter->latest.valid_mask = SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO |
                                SYSTEM_IMU_VALID_TEMPERATURE;
    adapter->latest.quality_flags = native->quality_flags | SYSTEM_IMU_QUALITY_TIME_UNCERTAIN;
    for (axis = 0U; axis < SENSOR_IMU_AXIS_COUNT; axis++)
    {
        adapter->latest.accel_raw[axis] = native->accel_raw[axis];
        adapter->latest.gyro_raw[axis] = native->gyro_raw[axis];
        adapter->latest.accel_b_mps2[axis] = native->accel_b_mps2[axis];
        adapter->latest.gyro_b_radps[axis] = native->gyro_b_radps[axis];
    }
    adapter->health.online = 1U;
    adapter->health.healthy = ((native->quality_flags & SENSOR_IMU_QUALITY_CLIPPED) == 0U);
    adapter->health.health_flags = native->quality_flags | SENSOR_IMU_QUALITY_TIME_UNCERTAIN;
    adapter->health.sample_count = native->sequence;
    adapter->health.last_sample_timestamp_us = native->sample_timestamp_us;
    adapter->health.last_receive_timestamp_us = native->receive_timestamp_us;
    PlatformCritical_Exit(lock);
}

static uint8_t SensorImuAdapter_DataReadyGet(SensorImuAdapter *adapter)
{
    if (adapter->spi_resources.drdy >= PLATFORM_GPIO_COUNT) { return 1U; }
    adapter->drdy_seen |= PlatformGpio_IrqConsume(adapter->spi_resources.drdy);
    if (adapter->spi_resources.auxiliary_drdy < PLATFORM_GPIO_COUNT)
    {
        adapter->auxiliary_drdy_seen |= PlatformGpio_IrqConsume(adapter->spi_resources.auxiliary_drdy);
        if (adapter->auxiliary_drdy_seen == 0U) { return 0U; }
    }
    if (adapter->drdy_seen == 0U) { return 0U; }
    adapter->drdy_seen = 0U;
    adapter->auxiliary_drdy_seen = 0U;
    return 1U;
}

static SystemDeviceResult SensorImuAdapter_SyncReadyGet(SensorImuAdapter *adapter,
    uint64_t now_us)
{
    uint8_t gyro;
    uint8_t ready;
    uint32_t start_us = 0U;
    uint32_t current_us = (uint32_t)now_us;
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((adapter->spi_resources.drdy >= PLATFORM_GPIO_COUNT) ||
        (adapter->spi_resources.auxiliary_drdy >= PLATFORM_GPIO_COUNT) ||
        (adapter->spi_resources.drdy == adapter->spi_resources.auxiliary_drdy))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    gyro = PlatformGpio_IrqConsume(adapter->spi_resources.auxiliary_drdy);
    ready = PlatformGpio_IrqConsume(adapter->spi_resources.drdy);
    memcpy(&start_us, adapter->driver.fifo_pending, sizeof(start_us));
    if (((gyro != 0U) && (adapter->auxiliary_drdy_seen != 0U)) ||
        ((adapter->auxiliary_drdy_seen != 0U) && (current_us - start_us > 2500U)) ||
        ((ready != 0U) && (gyro == 0U) && (adapter->auxiliary_drdy_seen == 0U)))
    {
        adapter->auxiliary_drdy_seen = 0U;
        adapter->driver.history_reset = 1U;
        adapter->driver.time_errors++;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    if (gyro != 0U)
    {
        adapter->auxiliary_drdy_seen = 1U;
        memcpy(adapter->driver.fifo_pending, &current_us, sizeof(current_us));
    }
    if ((ready == 0U) || (adapter->auxiliary_drdy_seen == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    adapter->auxiliary_drdy_seen = 0U;
    if ((adapter->driver.last_sample_us != 0U) &&
        ((now_us <= adapter->driver.last_sample_us) ||
         (now_us - adapter->driver.last_sample_us < 1500U) ||
         (now_us - adapter->driver.last_sample_us > 4000U)))
    {
        adapter->driver.history_reset = 1U;
        adapter->driver.time_errors++;
        adapter->driver.last_sample_us = 0U;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SensorImuAdapter_ReadAndPublish(SensorImuAdapter *adapter,
    uint64_t now_us)
{
    SensorImuResult result;
    SensorImuSample sample;
    SensorImuState previous_state = adapter->driver.state;
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->driver.profile->sync_pair_required != 0U)
    {
        SystemDeviceResult ready = SensorImuAdapter_SyncReadyGet(adapter, now_us);
        if (ready != SYSTEM_DEVICE_OK) { return ready; }
    }
    else if ((adapter->driver.state == SENSOR_IMU_READY) &&
        (adapter->driver.profile->fifo_frame_length == 0U) &&
        (SensorImuAdapter_DataReadyGet(adapter) == 0U)) { return SYSTEM_DEVICE_NOT_READY; }
    if (adapter->driver.profile->fifo_frame_length != 0U)
    {
        uint8_t count;
        result = SensorImu_DrainFifo(&adapter->driver, now_us, now_us, &sample, 1U, &count);
    }
    else { result = SensorImu_Read(&adapter->driver, now_us, now_us, &sample); }
    if (result == SENSOR_IMU_NOT_READY) { return SYSTEM_DEVICE_NOT_READY; }
    if (result != SENSOR_IMU_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    if (adapter->driver.profile->sync_pair_required != 0U)
    {
        uint8_t crossed = PlatformGpio_IrqConsume(adapter->spi_resources.auxiliary_drdy);
        crossed |= PlatformGpio_IrqConsume(adapter->spi_resources.drdy);
        if (crossed != 0U)
        {
            adapter->driver.history_reset = 1U;
            adapter->driver.time_errors++;
            /* A torn first pair must not open configuration/start admission. */
            adapter->driver.state = previous_state;
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
    }
    sample.quality_flags |= SENSOR_IMU_QUALITY_TIME_UNCERTAIN;
    SensorImuAdapter_Publish(adapter, &sample);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SensorImuAdapter_ProcessOwned(SensorImuAdapter *adapter)
{
    SensorImuResult result;
    uint64_t now_us = PlatformTime_Us();
    if ((adapter == NULL) || (adapter->started == 0U))
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->driver.state != SENSOR_IMU_READY)
    {
        result = SensorImu_ProcessConfigure(&adapter->driver, now_us);
        if ((result != SENSOR_IMU_BUSY) && (result != SENSOR_IMU_NOT_READY) &&
            (result != SENSOR_IMU_OK))
        {
            adapter->health.healthy = 0U;
            adapter->health.error_count++;
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
    }
    if ((adapter->driver.state != SENSOR_IMU_READY) &&
        (adapter->driver.state != SENSOR_IMU_SAMPLE_VERIFY)) { return SYSTEM_DEVICE_NOT_READY; }
    return SensorImuAdapter_ReadAndPublish(adapter, now_us);
}

SystemDeviceResult SensorImuAdapter_Process(SensorImuAdapter *adapter)
{
    SystemDeviceResult result;
    PlatformCriticalState lock;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    lock = PlatformCritical_Enter();
    if (adapter->processing != 0U)
    {
        PlatformCritical_Exit(lock);
        return SYSTEM_DEVICE_BUSY;
    }
    adapter->processing = 1U;
    PlatformCritical_Exit(lock);
    result = SensorImuAdapter_ProcessOwned(adapter);
    lock = PlatformCritical_Enter();
    adapter->processing = 0U;
    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_NOT_READY))
    {
        adapter->health.healthy = 0U;
        adapter->health.error_count++;
    }
    PlatformCritical_Exit(lock);
    return result;
}

SystemDeviceResult SensorImuAdapter_HealthGet(SensorImuAdapter *adapter,
    SystemDeviceHealth *health)
{
    uint64_t now_us = PlatformTime_Us();
    if ((adapter == NULL) || (health == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        *health = adapter->health;
        PlatformCritical_Exit(lock);
    }
    if ((health->sample_count == 0U) || (now_us < health->last_receive_timestamp_us) ||
        (now_us - health->last_receive_timestamp_us > SENSOR_ADAPTER_STALE_US))
    {
        health->online = 0U;
        health->healthy = 0U;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_SampleGet(SensorImuAdapter *adapter,
    SystemImuSample *sample, uint8_t consume)
{
    PlatformCriticalState lock;
    if ((adapter == NULL) || (sample == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if ((adapter->driver.state != SENSOR_IMU_READY) || (adapter->latest.sequence == 0U) ||
        ((consume != 0U) && (adapter->consumed_sequence == adapter->latest.sequence)))
    {
        PlatformCritical_Exit(lock);
        return SYSTEM_DEVICE_NOT_READY;
    }
    *sample = adapter->latest;
    if (consume != 0U) { adapter->consumed_sequence = sample->sequence; }
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SensorImuAdapter_ProfileConfigGet(SensorImuAdapter *adapter,
    SystemImuConfig *config)
{
    const SensorImuProfile *profile;
    if ((adapter == NULL) || (config == NULL) || (adapter->driver.profile == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    profile = adapter->driver.profile;
    memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_IMU_CFG_OUTPUT_RATE | SYSTEM_IMU_CFG_ACCEL_RANGE |
                             SYSTEM_IMU_CFG_GYRO_RANGE;
    config->output_rate_hz = (uint16_t)((1000000U + profile->sample_period_us / 2U) /
                                     profile->sample_period_us);
    /* Nominal advertised full scales are profile data, not inferred from ST
     * sensitivities, whose positive full scale differs from 32768 * LSB. */
    config->accel_range_g = (profile->accel_full_scale_g > 0.0F) ?
        profile->accel_full_scale_g : 16.0F;
    config->gyro_range_dps = 2000.0F;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_ConfigGet(SensorImuAdapter *adapter,
    SystemImuConfig *config)
{
    SystemDeviceResult result = SensorImuAdapter_ProfileConfigGet(adapter, config);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (adapter->driver.profile_verified == 0U)
    { config->requested_mask = 0U; return SYSTEM_DEVICE_NOT_READY; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_Init(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, PlatformI2cId bus_id,
    uint16_t address_7bit, uint32_t source_id)
{
    return SensorImuAdapter_InitI2c(adapter, profile, bus_id, bus_id,
        address_7bit, source_id);
}

static SystemDeviceResult SensorImuAdapter_ConfigValidate(SensorImuAdapter *adapter,
    const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    SystemImuConfig actual;
    uint32_t mismatch = 0U;
    if ((config == NULL) || (report == NULL) ||
        (SensorImuAdapter_ProfileConfigGet(adapter, &actual) != SYSTEM_DEVICE_OK))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->owner_active != 0U) { return SYSTEM_DEVICE_BUSY; }
    memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = actual.requested_mask;
    if (config->output_rate_hz != actual.output_rate_hz) { mismatch |= SYSTEM_IMU_CFG_OUTPUT_RATE; }
    if (config->accel_range_g != actual.accel_range_g) { mismatch |= SYSTEM_IMU_CFG_ACCEL_RANGE; }
    if (config->gyro_range_dps != actual.gyro_range_dps) { mismatch |= SYSTEM_IMU_CFG_GYRO_RANGE; }
    report->unsupported_required_mask = config->required_mask & ~actual.requested_mask;
    report->unsupported_optional_mask = config->requested_mask & ~actual.requested_mask;
    report->failed_mask = mismatch & config->requested_mask;
    if ((report->failed_mask != 0U) || (report->unsupported_required_mask != 0U))
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SensorImuAdapter_ConfigCheck(SensorImuAdapter *adapter,
    const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    SystemDeviceResult result = SensorImuAdapter_ConfigValidate(adapter, config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if ((adapter->driver.profile_verified == 0U) ||
        (SensorImu_Verify(&adapter->driver) != SENSOR_IMU_OK))
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask & report->supported_mask;
    report->success = 1U;
    return SYSTEM_DEVICE_ALREADY_MATCHED;
}

SystemDeviceResult SensorImuAdapter_ConfigApply(SensorImuAdapter *adapter,
    const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    uint32_t attempt;
    SystemDeviceResult result = SensorImuAdapter_ConfigValidate(adapter, config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    SILVERSTAR_ASSERT_OBJECT(adapter, SensorImuAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    /* Startup owner only. The bound covers Bosch's 1 s feature boot plus
     * reset, profile readback and at least one actual sample; ISR never waits. */
    for (attempt = 0U; attempt < 2500U; attempt++)
    {
        if (adapter->driver.state == SENSOR_IMU_READY)
        {
            result = SensorImuAdapter_ConfigCheck(adapter, config, report);
            report->applied_mask = report->matched_mask;
            return result;
        }
        result = SensorImuAdapter_Process(adapter);
        if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_NOT_READY))
        { report->failed_mask = config->requested_mask; return result; }
        PlatformTime_DelayMs(1U);
    }
    report->failed_mask = config->requested_mask;
    return SYSTEM_DEVICE_TIMEOUT;
}
