#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "platform_critical.h"
#include "project_device_instances.h"
#include "system_barometer.h"
#include "system_barometer_cold.h"
#include "system_time.h"

static uint64_t s_now = 1000000ULL;
static uint8_t s_primary;
static uint32_t s_process_time_step;
static uint8_t s_running[4];
static uint32_t s_init[4], s_start[4], s_stop[4], s_process[4], s_read[4];
static SystemDeviceResult s_init_result[4], s_start_result[4], s_stop_result[4];
static SystemBarometerSample s_sample[4];
static SystemDeviceHealth s_health[4];
static unsigned int s_operations[64];
static unsigned int s_operation_count;

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass cls)
{ return cls == SYSTEM_DEVICE_CLASS_BAROMETER ? 4U : 0U; }
SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass cls, uint8_t instance, SystemDeviceDescriptor *descriptor)
{
    assert(cls == SYSTEM_DEVICE_CLASS_BAROMETER && instance < 4U);
    (void)memset(descriptor, 0, sizeof(*descriptor));
    descriptor->flags = instance == s_primary ? SYSTEM_DESCRIPTOR_FLAG_PRIMARY : 0U;
    return SYSTEM_DEVICE_OK;
}
static void TestOperation(unsigned int operation)
{
    assert(s_operation_count < 64U);
    s_operations[s_operation_count++] = operation;
}
SystemDeviceResult ProjectBarometerInstance_Init(uint8_t instance)
{
    assert(instance < 4U); s_init[instance]++; TestOperation(10U + instance);
    return s_init_result[instance];
}
SystemDeviceResult ProjectBarometerInstance_Start(uint8_t instance)
{
    assert(instance < 4U); s_start[instance]++; TestOperation(20U + instance);
    s_running[instance] = 1U;
    return s_start_result[instance];
}
SystemDeviceResult ProjectBarometerInstance_Stop(uint8_t instance)
{
    assert(instance < 4U); s_stop[instance]++; TestOperation(30U + instance);
    if (s_stop_result[instance] == SYSTEM_DEVICE_OK) { s_running[instance] = 0U; }
    return s_stop_result[instance];
}
SystemDeviceResult ProjectBarometerInstance_Process(uint8_t instance)
{
    assert(instance < 4U && s_running[instance] != 0U);
    s_process[instance]++;
    if (s_process_time_step != 0U)
    {
        s_now += s_process_time_step;
        s_sample[instance].sequence++;
        s_sample[instance].sample_timestamp_us = s_now;
        s_sample[instance].receive_timestamp_us = s_now;
    }
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectBarometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    assert(instance < 4U); *health = s_health[instance]; return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(uint8_t instance, SystemBarometerSample *sample)
{
    assert(instance < 4U); s_read[instance]++; *sample = s_sample[instance]; return SYSTEM_DEVICE_OK;
}
static void TestReset(uint8_t primary)
{
    assert(SystemBarometerCold_Stop() == SYSTEM_DEVICE_OK);
    s_primary = primary; s_now = 1000000ULL; s_process_time_step = 0U; s_operation_count = 0U;
    (void)memset(s_running, 0, sizeof(s_running));
    (void)memset(s_init, 0, sizeof(s_init)); (void)memset(s_start, 0, sizeof(s_start));
    (void)memset(s_stop, 0, sizeof(s_stop)); (void)memset(s_process, 0, sizeof(s_process));
    (void)memset(s_read, 0, sizeof(s_read));
    (void)memset(s_init_result, 0, sizeof(s_init_result));
    (void)memset(s_start_result, 0, sizeof(s_start_result));
    (void)memset(s_stop_result, 0, sizeof(s_stop_result));
    (void)memset(s_sample, 0, sizeof(s_sample)); (void)memset(s_health, 0, sizeof(s_health));
    for (uint8_t instance = 0U; instance < 4U; instance++)
    {
        s_sample[instance].supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
        s_sample[instance].valid_fields = s_sample[instance].supported_fields;
        s_sample[instance].pressure_pa = 101325.0F;
        s_sample[instance].altitude_m = 5000.0F + (float)instance;
        s_sample[instance].pressure_raw_pa = 101325;
        s_sample[instance].altitude_raw_cm = 500000 + instance;
        s_sample[instance].sequence = 99U;
        s_sample[instance].sample_timestamp_us = s_now;
        s_sample[instance].receive_timestamp_us = s_now;
        s_health[instance].started = 1U; s_health[instance].online = 1U; s_health[instance].healthy = 1U;
    }
    assert(SystemBarometerCold_Init() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_Start() == SYSTEM_DEVICE_OK);
}
static void TestColdOrderAndIdentity(void)
{
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    float height;
    TestReset(2U);
    assert(s_init[2] == 1U && s_start[2] == 1U && s_init[0] == 0U && s_init[1] == 0U && s_init[3] == 0U);
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 1U);
    assert(sample.altitude_m == 5002.0F && sample.altitude_raw_cm == 500002);
    assert(SystemBarometer_AltitudeResolve(&sample, &height) == SYSTEM_DEVICE_OK && fabsf(height) < 0.01F);
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 1U);
    assert(s_process[0] == 0U && s_process[1] == 0U && s_process[3] == 0U);
    assert(s_read[0] == 0U && s_read[1] == 0U && s_read[3] == 0U);
    s_health[2].healthy = 0U; s_now += 10000U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY && s_stop[2] == 0U);
    assert(SystemBarometerCold_HealthGet(&health) == SYSTEM_DEVICE_NOT_READY && health.healthy == 0U);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    s_health[2].healthy = 1U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 1U);
    s_now = 1250001U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 0U && s_stop[2] == 1U && s_start[0] == 1U);
    assert(s_operations[2] == 32U && s_operations[3] == 10U && s_operations[4] == 20U);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    /* Reject a warm shared transport's cached sample predating selection. */
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    s_sample[0].sample_timestamp_us = s_now; s_sample[0].receive_timestamp_us = s_now;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 2U);
    s_sample[0].sequence = UINT32_MAX; s_now++;
    s_sample[0].sample_timestamp_us = s_now; s_sample[0].receive_timestamp_us = s_now;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 3U);
    s_sample[0].sequence = 0U; s_now++;
    s_sample[0].sample_timestamp_us = s_now; s_sample[0].receive_timestamp_us = s_now;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK && sample.sequence == 4U);
}
static void TestFailedStopAndPartialStart(void)
{
    SystemBarometerSample sample;
    TestReset(0U);
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    s_now = 1250001U; s_stop_result[0] = SYSTEM_DEVICE_IO_ERROR;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_IO_ERROR);
    assert(SystemBarometerCold_ActiveGet() == SYSTEM_BAROMETER_COLD_INSTANCE_NONE);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    assert(s_init[1] == 0U && s_running[0] != 0U);
    assert(SystemBarometerCold_Start() == SYSTEM_DEVICE_BAD_STATE);
    s_stop_result[0] = SYSTEM_DEVICE_OK;
    assert(SystemBarometerCold_Stop() == SYSTEM_DEVICE_OK);
    s_init_result[1] = SYSTEM_DEVICE_IO_ERROR; s_start_result[2] = SYSTEM_DEVICE_IO_ERROR;
    assert(SystemBarometerCold_Start() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 3U && s_stop[2] == 1U);
    assert(s_running[0] == 0U && s_running[1] == 0U && s_running[2] == 0U && s_running[3] == 1U);
    s_now += SYSTEM_BAROMETER_COLD_BACKUP_FIRST_SAMPLE_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_PRESENT);
    assert(SystemBarometerCold_ActiveGet() == SYSTEM_BAROMETER_COLD_INSTANCE_NONE);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    assert(s_stop[3] == 1U);
}
static void TestPressureDatumReject(void)
{
    float altitude;
    SystemBarometerSample sample;
    TestReset(0U);
    sample = s_sample[0]; sample.valid_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    assert(SystemBarometer_AltitudeResolve(&sample, &altitude) == SYSTEM_DEVICE_NOT_READY);
    sample = s_sample[0]; sample.pressure_pa = NAN;
    assert(SystemBarometer_AltitudeResolve(&sample, &altitude) == SYSTEM_DEVICE_NOT_READY);
    sample = s_sample[0]; sample.pressure_pa = 100.0F;
    assert(SystemBarometer_AltitudeResolve(&sample, &altitude) == SYSTEM_DEVICE_NOT_READY);
    s_sample[0].valid_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    s_now += SYSTEM_BAROMETER_COLD_BACKUP_FIRST_SAMPLE_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK && SystemBarometerCold_ActiveGet() == 1U);
}
static void TestSampleProducedDuringProcess(void)
{
    SystemBarometerSample sample;
    TestReset(0U);
    s_process_time_step = 50U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK);
    assert(sample.receive_timestamp_us == s_now && sample.sequence == 1U);
    assert(s_read[1] == 0U && s_stop[0] == 0U);
    /* A timestamp genuinely ahead of the post-read clock stays invalid. */
    s_process_time_step = 0U;
    s_sample[0].receive_timestamp_us = s_now + 1U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    assert(s_stop[0] == 0U);
}
static void TestDelayedFirstSample(void)
{
    SystemBarometerSample sample;
    TestReset(0U);
    s_sample[0].valid_fields = 0U;
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_OK);
    s_now += 2000000ULL;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    assert(SystemBarometerCold_ActiveGet() == 0U && s_stop[0] == 0U);
    s_sample[0].valid_fields = s_sample[0].supported_fields;
    s_sample[0].sample_timestamp_us = s_now;
    s_sample[0].receive_timestamp_us = s_now;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK);
    assert(s_start[1] == 0U);
}
static void TestFirstSampleWindowBoundary(void)
{
    TestReset(2U);
    s_sample[2].valid_fields = 0U;
    s_now += 5000000ULL; /* Startup phases precede the configuration wait. */
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_BAD_STATE);
    s_now += SYSTEM_STARTUP_CONFIGURATION_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    assert(SystemBarometerCold_ActiveGet() == 2U && s_start[0] == 0U);
    assert(SystemBarometerCold_StartupCommunicationBegin(s_now) == SYSTEM_DEVICE_OK);
    s_now += SYSTEM_STARTUP_COMMUNICATION_TIMEOUT_US - 1ULL;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    s_now++;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(s_stop[2] == 1U && s_start[0] == 1U && SystemBarometerCold_ActiveGet() == 0U);
    /* Even before the global completion hook, a replacement gets250ms,
     * rather than the expired global timer or a renewed122-second timer. */
    s_sample[0].valid_fields = 0U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    s_now += SYSTEM_BAROMETER_COLD_BACKUP_FIRST_SAMPLE_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 1U && s_stop[0] == 1U);
}
static void TestRuntimeBadBackupDoesNotBlockNext(void)
{
    SystemBarometerSample sample;
    TestReset(0U);
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    s_now += SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US + 1ULL;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 1U && s_stop[0] == 1U);
    s_sample[1].valid_fields = 0U;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    s_now += SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 2U && s_stop[1] == 1U);
    s_sample[2].sample_timestamp_us = s_now;
    s_sample[2].receive_timestamp_us = s_now;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_SampleGet(&sample) == SYSTEM_DEVICE_OK);
    assert(s_now - 1000000ULL == 500001ULL && s_start[3] == 0U);
}
static void TestEarlyStartupEndRevokesGrace(void)
{
    TestReset(0U);
    s_sample[0].valid_fields = 0U;
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_OK);
    s_now += 10000ULL;
    assert(SystemBarometerCold_StartupCommunicationBegin(s_now) == SYSTEM_DEVICE_OK);
    s_now += SYSTEM_STARTUP_COMMUNICATION_TIMEOUT_US - 1ULL;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_NOT_READY);
    assert(SystemBarometerCold_ActiveGet() == 0U);
    s_now++;
    assert(SystemBarometerCold_StartupWindowEnd() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 1U && s_stop[0] == 1U);
    s_sample[1].valid_fields = 0U;
    s_now += SYSTEM_BAROMETER_COLD_BACKUP_FIRST_SAMPLE_TIMEOUT_US;
    assert(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    assert(SystemBarometerCold_ActiveGet() == 2U && s_stop[1] == 1U);
    assert(SystemBarometerCold_StartupWindowBegin(s_now) == SYSTEM_DEVICE_BAD_STATE);
}
int main(void)
{
    TestEarlyStartupEndRevokesGrace();
    TestRuntimeBadBackupDoesNotBlockNext();
    TestFirstSampleWindowBoundary();
    TestDelayedFirstSample();
    TestColdOrderAndIdentity(); TestFailedStopAndPartialStart(); TestPressureDatumReject();
    TestSampleProducedDuringProcess();
    assert(SystemBarometerCold_Stop() == SYSTEM_DEVICE_OK);
    (void)puts("cold barometer order/cache/stop/start/exhaustion/wrap/pressure datum PASS");
    return 0;
}
