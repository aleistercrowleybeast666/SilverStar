#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mpu6050_instance.h"
#include "project_resources.h"
#include "project_device_instances.h"
#include "platform_critical.h"
#include "platform_gpio.h"
#include "system_source_selector.h"
#include "system_time.h"
#if !defined(TEST_ORDINARY)
#include "system_health.h"
#include "system_profile.h"
#include "system_navigation_profile.h"
#include "system_startup.h"
#include "system_output_if.h"
#include "system_calibration.h"
#include "system_alignment.h"
#endif

static uint64_t s_now = 1000000ULL;
static uint8_t s_registers[256];
static uint8_t s_probe_fail, s_reset_fail, s_reset_stuck, s_ignore_write, s_sample_read_fail;
static uint32_t s_reads, s_writes, s_delays, s_lock_depth;
static uint32_t s_max_io;
static uint8_t s_resource_missing;
#if !defined(TEST_ORDINARY)
static SystemStartupReport s_report;
static uint8_t s_cal_ready = 1U, s_align_ready = 1U;
static const SystemProfile s_profile = { .enabled_capabilities = SYSTEM_CAPABILITY_IMU | SYSTEM_CAPABILITY_OUTPUT,
    .required_capabilities = SYSTEM_CAPABILITY_IMU | SYSTEM_CAPABILITY_OUTPUT, .output_channel_count = 1U };
static const SystemNavigationProfile s_navigation = { .alignment_algorithm = SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW };
const SystemProfile *SystemProfile_Get(void) { return &s_profile; }
const SystemNavigationProfile *SystemNavigationProfile_Get(void) { return &s_navigation; }
const SystemStartupReport *SystemStartup_GetReport(void) { return &s_report; }
uint8_t SystemCalibration_IsReady(void) { return s_cal_ready; }
uint8_t SystemAlignment_IsReady(void) { return s_align_ready; }
SystemDeviceResult SystemCapabilities_Refresh(void) { return SYSTEM_DEVICE_OK; }
void SystemCapabilities_Get(SystemCapabilities *capabilities)
{
    SystemDeviceHealth health;
    memset(capabilities, 0, sizeof(*capabilities));
    capabilities->present_mask = SYSTEM_CAPABILITY_IMU | SYSTEM_CAPABILITY_OUTPUT;
    capabilities->healthy_mask = SYSTEM_CAPABILITY_OUTPUT;
    if (SystemImu_HealthGet(&health) == SYSTEM_DEVICE_OK && health.healthy && health.online)
    { capabilities->healthy_mask |= SYSTEM_CAPABILITY_IMU; }
}
SystemDeviceResult SystemOutput_StatusGet(uint8_t channel, SystemOutputStatus *status)
{
    assert(channel == 1U); memset(status, 0, sizeof(*status)); status->state = SYSTEM_OUTPUT_SAFE;
    return SYSTEM_DEVICE_OK;
}
#endif

uint64_t PlatformTime_Us(void) { return s_now; }
uint32_t PlatformTime_Ms(void) { return (uint32_t)(s_now / 1000ULL); }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
void PlatformTime_DelayMs(uint32_t delay) { s_delays++; s_now += (uint64_t)delay * 1000ULL; }
PlatformCriticalState PlatformCritical_Enter(void) { s_lock_depth++; return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; assert(s_lock_depth > 0U); s_lock_depth--; }
uint8_t PlatformGpio_IrqConsume(PlatformGpioId id) { (void)id; return 0U; }

SystemDeviceResult ProjectMpu6050Resources_Get(uint8_t instance, ProjectMpu6050Resources *resources)
{
    if ((instance != 0U) || s_resource_missing) { return SYSTEM_DEVICE_NOT_PRESENT; }
    resources->i2c = PLATFORM_I2C_1; resources->time = PLATFORM_TIME_1;
    resources->axis_map[0] = -2; resources->axis_map[1] = 1; resources->axis_map[2] = 3;
    return SYSTEM_DEVICE_OK;
}
PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id, uint16_t address, uint16_t reg,
    PlatformI2cMemoryAddressSize size, uint8_t *data, uint16_t length, uint32_t timeout)
{
    assert(id == PLATFORM_I2C_1 && address == 0x68U && size == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT);
    assert(timeout == 2U && reg + length <= 256U && s_lock_depth == 0U);
    s_reads++;
    if (reg == 117U && s_probe_fail) { return PLATFORM_IO_ERROR; }
    if ((reg == 58U || reg == 59U) && s_sample_read_fail) { return PLATFORM_IO_ERROR; }
    memcpy(data, &s_registers[reg], length); return PLATFORM_OK;
}
PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id, uint16_t address, uint16_t reg,
    PlatformI2cMemoryAddressSize size, const uint8_t *data, uint16_t length, uint32_t timeout)
{
    assert(id == PLATFORM_I2C_1 && address == 0x68U && size == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT);
    assert(timeout == 2U && reg + length <= 256U && s_lock_depth == 0U);
    s_writes++;
    if (reg == 107U && data[0] == 128U && s_reset_fail) { return PLATFORM_IO_ERROR; }
    if (!s_ignore_write) { memcpy(&s_registers[reg], data, length); }
    if (reg == 107U && data[0] == 128U && !s_reset_stuck) { s_registers[reg] = 0U; }
    return PLATFORM_OK;
}
uint8_t SystemDescriptor_DeviceClassInstanceCountGet(SystemDeviceClass device_class)
{ return device_class == SYSTEM_DEVICE_CLASS_IMU ? 1U : 0U; }
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass device_class, uint8_t instance,
    SystemDeviceDescriptor *descriptor)
{
    if (device_class != SYSTEM_DEVICE_CLASS_IMU || instance != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    memset(descriptor, 0, sizeof(*descriptor)); descriptor->device_class = device_class;
    descriptor->flags = SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_REQUIRED | SYSTEM_DESCRIPTOR_FLAG_PRIMARY;
    return SYSTEM_DEVICE_OK;
}

static void Tick(uint32_t ms)
{
    uint32_t io = s_reads + s_writes;
    s_now += (uint64_t)ms * 1000ULL; SystemImu_Process();
    io = s_reads + s_writes - io; if (io > s_max_io) { s_max_io = io; }
    assert(io <= 3U && s_delays == 0U && s_lock_depth == 0U);
}
static void Ready(void)
{
    SystemImuSample sample; uint32_t index;
    for (index = 0U; index < 3400U; index++)
    {
        Tick(10U);
        if (SystemImu_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK) { return; }
    }
    assert(!"same-instance physical recovery never produced a verified fresh sample");
}
static void Initial(void)
{
    SystemDeviceResult result;
    s_registers[117] = 104U; s_registers[58] = 1U;
    s_registers[59] = 0x10U; s_registers[61] = 0x08U;
    result = SystemImu_Init();
#if defined(TEST_ORDINARY) || defined(TEST_BASELINE)
    assert(result == SYSTEM_DEVICE_OK);
#else
    assert(result == SYSTEM_DEVICE_CONFIG_DELEGATED);
#endif
    result = SystemImu_Start(); assert(result == SYSTEM_DEVICE_OK || result == SYSTEM_DEVICE_CONFIG_DELEGATED);
}
int main(int argc, char **argv)
{
    unsigned int which; uint32_t index; uint8_t active; SystemImuSample before, after;
    SystemDeviceHealth health; SystemImuIoDetail detail; uint32_t old_generation;
#if !defined(TEST_ORDINARY)
    SystemStartupReport history; SystemHealthSnapshot health_snapshot;
#endif
    assert(argc == 2); which = (unsigned int)strtoul(argv[1], NULL, 10);
    s_registers[117] = 104U; s_registers[58] = 1U;
    if (which == 15U)
    {
        uint32_t previous;
        s_probe_fail = 1U; assert(SystemImu_Init() == SYSTEM_DEVICE_VERIFY_FAILED);
        assert(SystemImu_Start() == SYSTEM_DEVICE_NOT_READY); previous = s_reads;
        for (index = 0U; index < 200U; index++) { Tick(1000U); }
        assert(s_reads == previous && SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_NOT_READY);
    }
    else if (which == 16U)
    {
        uint32_t previous;
        s_reset_stuck = 1U; Initial();
        for (index = 0U; index < 150U; index++) { Tick(10U); }
        previous = s_reads; s_reset_stuck = 0U;
        for (index = 0U; index < 200U; index++) { Tick(1000U); }
        assert(s_reads == previous && SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_NOT_READY);
    }
    else if (which <= 5U || which == 7U)
    {
        if (which == 1U || which == 7U) { s_probe_fail = 1U; }
        if (which == 2U) { s_reset_fail = 1U; }
        if (which == 3U) { s_reset_stuck = 1U; }
        if (which == 4U) { s_ignore_write = 1U; }
        if (which == 5U) { s_registers[58] = 0U; }
        if (which == 7U) { s_now = ((uint64_t)UINT32_MAX - 500ULL) * 1000ULL; }
        (void)SystemImu_Init(); (void)SystemImu_Start();
        for (index = 0U; index < 180U; index++) { Tick(10U); }
        s_probe_fail = s_reset_fail = s_reset_stuck = s_ignore_write = 0U; s_registers[58] = 1U;
        Ready();
    }
    else if (which == 6U)
    {
        uint32_t previous;
        s_probe_fail = 1U; (void)SystemImu_Init(); (void)SystemImu_Start();
        /* Beyond 255 failures: no total-attempt limit, 32 s backoff persists. */
        for (index = 0U; index < 300U; index++)
        {
            previous = s_reads; Tick(32000U); assert(s_reads == previous + 2U);
            previous = s_reads; Tick(1U); assert(s_reads == previous);
        }
        assert(SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_NOT_READY);
        s_probe_fail = 0U; Ready();
    }
    else
    {
        Initial(); Ready(); assert(SystemImu_LatestSampleGet(&before) == SYSTEM_DEVICE_OK);
        assert(SystemImu_IoDetailGet(&detail) == SYSTEM_DEVICE_OK);
        old_generation = detail.config_generation;
        if (which == 8U || which == 9U) { assert(SystemSourceSelector_ImuSelectAndLock() == SYSTEM_DEVICE_OK); }
        if (which == 8U || which == 9U || which == 10U || which == 11U)
        {
            if (which == 10U) { s_sample_read_fail = 1U; }
            else { s_probe_fail = 1U; s_now += 150000ULL; }
            Tick(1U);
            assert(SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_NOT_READY);
            assert(SystemImu_IoDetailGet(&detail) == SYSTEM_DEVICE_OK && detail.config_generation_valid == 0U);
            assert(SystemImu_HealthGet(&health) == SYSTEM_DEVICE_OK && !health.online && !health.healthy);
            if (which == 8U || which == 9U)
            { assert(SystemSourceSelector_ImuActiveInstanceGet(&active) == SYSTEM_DEVICE_OK && active == 0U); }
            s_probe_fail = s_sample_read_fail = 0U; Ready(); assert(SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_OK);
            assert(SystemImu_IoDetailGet(&detail) == SYSTEM_DEVICE_OK && detail.config_generation > old_generation);
            assert(after.sequence > before.sequence && after.receive_timestamp_us > before.receive_timestamp_us);
            assert((after.quality_flags & SYSTEM_IMU_QUALITY_HISTORY_RESET) != 0U);
            assert(after.accel_b_mps2[0] < 0.0F && after.accel_b_mps2[1] > 0.0F);
            if (which == 9U)
            {
                assert(Mpu6050ImuInstance_Init(0U) == SYSTEM_DEVICE_BUSY);
                assert(SystemSourceSelector_ImuActiveInstanceGet(&active) == SYSTEM_DEVICE_OK && active == 0U);
            }
        }
        if (which == 12U)
        {
            uint32_t old; assert(SystemImu_Stop() == SYSTEM_DEVICE_OK); old = s_reads;
            for (index = 0U; index < 80U; index++) { Tick(1000U); }
            assert(s_reads == old && SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_NOT_READY);
        }
#if !defined(TEST_ORDINARY)
        if (which == 13U || which == 14U)
        {
            assert(SystemImu_RuntimeOwnerActivate() == SYSTEM_DEVICE_OK);
            s_report.completed = 1U; s_report.mission_capable = (which == 14U) ? 1U : 0U;
            s_report.devices[SYSTEM_STARTUP_DEVICE_IMU].init_result = SYSTEM_DEVICE_VERIFY_FAILED;
            history = s_report;
            s_now += 150000ULL; Tick(1U); Ready();
            {
                SystemImuConfig config = { .requested_mask = SYSTEM_IMU_CFG_OUTPUT_RATE,
                    .required_mask = SYSTEM_IMU_CFG_OUTPUT_RATE, .output_rate_hz = 200U };
                SystemDeviceConfigReport config_report;
                assert(Mpu6050ImuInstance_ConfigApply(0U, &config, &config_report) == SYSTEM_DEVICE_BUSY);
            }
            SystemHealth_Init(); SystemHealth_SetAttitudeReady(1U); SystemHealth_Process();
            assert(memcmp(&history, &s_report, sizeof(history)) == 0);
            if (which == 13U)
            {
                SystemHealth_GetSnapshot(&health_snapshot);
                assert(!health_snapshot.ready && (health_snapshot.start_blocking_mask & SYSTEM_HEALTH_BLOCK_STARTUP_FAILED));
            }
            else
            {
                s_cal_ready = 0U; SystemHealth_Process(); SystemHealth_GetSnapshot(&health_snapshot);
                assert(!health_snapshot.ready && (health_snapshot.start_blocking_mask & SYSTEM_HEALTH_BLOCK_CALIBRATION_NOT_READY));
                s_cal_ready = 1U; s_align_ready = 0U; SystemHealth_Process(); SystemHealth_GetSnapshot(&health_snapshot);
                /* Alignment boundary models missing/stale initial alignment or origin; no automatic re-alignment. */
                assert(!health_snapshot.ready && (health_snapshot.start_blocking_mask & SYSTEM_HEALTH_BLOCK_ALIGNMENT_NOT_READY));
            }
        }
#endif
    }
    printf("mpu_recovery sequence=%u PASS max_io_per_tick=%lu delays=%lu\n", which,
        (unsigned long)s_max_io, (unsigned long)s_delays); return 0;
}
