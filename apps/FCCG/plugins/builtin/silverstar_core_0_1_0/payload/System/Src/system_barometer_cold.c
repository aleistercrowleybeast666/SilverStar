#include "system_barometer_cold.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_time.h"

typedef enum
{
    SystemBarometerColdStartup_Idle = 0,
    SystemBarometerColdStartup_Configuration,
    SystemBarometerColdStartup_Communication,
    SystemBarometerColdStartup_Complete
} SystemBarometerColdStartupStage;

typedef struct
{
    uint8_t order[PROJECT_BAROMETER_INSTANCE_COUNT_MAX];
    uint8_t count;
    uint8_t next_position;
    uint8_t active;
    uint8_t running;
    uint8_t sample_valid;
    uint8_t raw_known;
    uint8_t sample_ever_received;
    uint8_t startup_grace_instance;
    SystemBarometerColdStartupStage startup_stage;
    uint64_t startup_phase_started_us;
    uint64_t activated_us;
    uint64_t last_good_us;
    uint32_t raw_sequence;
    uint32_t logical_sequence;
    SystemBarometerSample sample;
    SystemDeviceHealth health;
} SystemBarometerColdState;

static SystemBarometerColdState s_cold = {
    .active = SYSTEM_BAROMETER_COLD_INSTANCE_NONE,
    .running = SYSTEM_BAROMETER_COLD_INSTANCE_NONE
};

static uint8_t SystemBarometerCold_Successful(SystemDeviceResult result)
{
    return (uint8_t)((result == SYSTEM_DEVICE_OK) ||
        (result == SYSTEM_DEVICE_ALREADY_MATCHED));
}

static void SystemBarometerCold_SelectionSet(uint8_t instance)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    s_cold.active = instance;
    s_cold.sample_valid = 0U;
    s_cold.raw_known = 0U;
    (void)memset(&s_cold.health, 0, sizeof(s_cold.health));
    PlatformCritical_Exit(state);
}

static SystemDeviceResult SystemBarometerCold_OrderBuild(void)
{
    uint8_t primary = 0U;
    uint8_t instance;
    uint8_t position = 1U;
    for (instance = 0U; instance < PROJECT_BAROMETER_INSTANCE_COUNT_MAX; instance++)
    {
        SystemDeviceDescriptor descriptor;
        if (instance >= s_cold.count) { break; }
        if (ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_BAROMETER,
            instance, &descriptor) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_INTERNAL_ERROR; }
        if ((descriptor.flags & SYSTEM_DESCRIPTOR_FLAG_PRIMARY) != 0U)
        { primary = instance; break; }
    }
    s_cold.order[0] = primary;
    for (instance = 0U; instance < PROJECT_BAROMETER_INSTANCE_COUNT_MAX; instance++)
    {
        if (instance >= s_cold.count) { break; }
        if (instance == primary) { continue; }
        SILVERSTAR_ASSERT(position < s_cold.count, SILVERSTAR_ASSERT_MODULE_SYSTEM,
            SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        s_cold.order[position++] = instance;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemBarometerCold_Stop(void)
{
    uint8_t running = s_cold.running;
    SystemBarometerCold_SelectionSet(SYSTEM_BAROMETER_COLD_INSTANCE_NONE);
    if (running == SYSTEM_BAROMETER_COLD_INSTANCE_NONE) { return SYSTEM_DEVICE_OK; }
    SILVERSTAR_ASSERT(running < s_cold.count, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    /* A failed stop retains the running identity and blocks all replacements. */
    if (SystemBarometerCold_Successful(ProjectBarometerInstance_Stop(running)) == 0U)
    { return SYSTEM_DEVICE_IO_ERROR; }
    s_cold.running = SYSTEM_BAROMETER_COLD_INSTANCE_NONE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemBarometerCold_NextSelect(uint8_t start)
{
    uint8_t step;
    SystemDeviceResult failure = SYSTEM_DEVICE_NOT_PRESENT;
    SILVERSTAR_ASSERT(s_cold.count <= PROJECT_BAROMETER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT(s_cold.running == SYSTEM_BAROMETER_COLD_INSTANCE_NONE,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (step = 0U; step < PROJECT_BAROMETER_INSTANCE_COUNT_MAX; step++)
    {
        uint8_t candidate;
        if (s_cold.next_position >= s_cold.count) { break; }
        candidate = s_cold.order[s_cold.next_position++];
        SILVERSTAR_ASSERT(candidate < s_cold.count, SILVERSTAR_ASSERT_MODULE_SYSTEM,
            SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        failure = ProjectBarometerInstance_Init(candidate);
        if (SystemBarometerCold_Successful(failure) == 0U) { continue; }
        SystemBarometerCold_SelectionSet(candidate);
        if (start == 0U) { return SYSTEM_DEVICE_OK; }
        s_cold.running = candidate; /* Start failure may have partial side effects. */
        failure = ProjectBarometerInstance_Start(candidate);
        if (SystemBarometerCold_Successful(failure) != 0U)
        {
            s_cold.activated_us = SystemTime_GetMonotonicUs();
            s_cold.last_good_us = s_cold.activated_us;
            return SYSTEM_DEVICE_OK;
        }
        if (SystemBarometerCold_Stop() != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    }
    SystemBarometerCold_SelectionSet(SYSTEM_BAROMETER_COLD_INSTANCE_NONE);
    return failure;
}

SystemDeviceResult SystemBarometerCold_Init(void)
{
    PlatformCriticalState state;
    if (SystemBarometerCold_Stop() != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    state = PlatformCritical_Enter();
    (void)memset(&s_cold, 0, sizeof(s_cold));
    s_cold.active = SYSTEM_BAROMETER_COLD_INSTANCE_NONE;
    s_cold.running = SYSTEM_BAROMETER_COLD_INSTANCE_NONE;
    PlatformCritical_Exit(state);
    s_cold.count = ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_BAROMETER);
    if ((s_cold.count < 2U) || (s_cold.count > PROJECT_BAROMETER_INSTANCE_COUNT_MAX))
    { s_cold.count = 0U; return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SystemBarometerCold_OrderBuild() != SYSTEM_DEVICE_OK)
    { s_cold.count = 0U; return SYSTEM_DEVICE_INTERNAL_ERROR; }
    return SystemBarometerCold_NextSelect(0U);
}

SystemDeviceResult SystemBarometerCold_Start(void)
{
    SystemDeviceResult result;
    if (s_cold.running != SYSTEM_BAROMETER_COLD_INSTANCE_NONE)
    { return SYSTEM_DEVICE_BAD_STATE; }
    if (s_cold.active == SYSTEM_BAROMETER_COLD_INSTANCE_NONE)
    { return SystemBarometerCold_NextSelect(1U); }
    SILVERSTAR_ASSERT(s_cold.active < s_cold.count, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    s_cold.running = s_cold.active;
    result = ProjectBarometerInstance_Start(s_cold.active);
    if (SystemBarometerCold_Successful(result) == 0U)
    {
        if (SystemBarometerCold_Stop() != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_IO_ERROR; }
        return SystemBarometerCold_NextSelect(1U);
    }
    s_cold.activated_us = SystemTime_GetMonotonicUs();
    s_cold.last_good_us = s_cold.activated_us;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemBarometerCold_StartupWindowBegin(uint64_t phase_started_us)
{
    const uint64_t now_us = SystemTime_GetMonotonicUs();
    if ((s_cold.active == SYSTEM_BAROMETER_COLD_INSTANCE_NONE) ||
        (s_cold.running == SYSTEM_BAROMETER_COLD_INSTANCE_NONE))
    { return SYSTEM_DEVICE_NOT_READY; }
    if ((s_cold.startup_stage != SystemBarometerColdStartup_Idle) ||
        (s_cold.sample_ever_received != 0U))
    { return SYSTEM_DEVICE_BAD_STATE; }
    if ((phase_started_us < s_cold.activated_us) || (phase_started_us > now_us))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT(s_cold.active == s_cold.running, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_cold.startup_grace_instance = s_cold.active;
    s_cold.startup_phase_started_us = phase_started_us;
    s_cold.startup_stage = SystemBarometerColdStartup_Configuration;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemBarometerCold_StartupCommunicationBegin(uint64_t phase_started_us)
{
    const uint64_t now_us = SystemTime_GetMonotonicUs();
    if (s_cold.startup_stage != SystemBarometerColdStartup_Configuration)
    { return SYSTEM_DEVICE_BAD_STATE; }
    if ((phase_started_us < s_cold.startup_phase_started_us) || (phase_started_us > now_us))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_cold.startup_phase_started_us = phase_started_us;
    s_cold.startup_stage = SystemBarometerColdStartup_Communication;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemBarometerCold_StartupWindowEnd(void)
{
    if ((s_cold.startup_stage != SystemBarometerColdStartup_Configuration) &&
        (s_cold.startup_stage != SystemBarometerColdStartup_Communication))
    { return SYSTEM_DEVICE_BAD_STATE; }
    s_cold.startup_stage = SystemBarometerColdStartup_Complete;
    return SYSTEM_DEVICE_OK;
}

static uint8_t SystemBarometerCold_FirstSamplePending(uint64_t now_us)
{
    SILVERSTAR_ASSERT(((uint32_t)s_cold.startup_stage <=
        (uint32_t)SystemBarometerColdStartup_Complete) &&
        (s_cold.sample_ever_received <= 1U), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_cold.sample_ever_received == 0U) &&
        (s_cold.active == s_cold.startup_grace_instance) &&
        ((s_cold.startup_stage == SystemBarometerColdStartup_Configuration) ||
         (s_cold.startup_stage == SystemBarometerColdStartup_Communication)))
    {
        const uint64_t timeout_us =
            s_cold.startup_stage == SystemBarometerColdStartup_Configuration ?
            SYSTEM_BAROMETER_COLD_FIRST_SAMPLE_TIMEOUT_US :
            SYSTEM_STARTUP_COMMUNICATION_TIMEOUT_US;
        SILVERSTAR_ASSERT(now_us >= s_cold.startup_phase_started_us,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
        return (uint8_t)((now_us - s_cold.startup_phase_started_us) <
            timeout_us);
    }
    /* This per-source activation budget never inherits a global config timer.
     * BMP/MS finite configuration/conversion states fit 250ms at <=10ms polling
     * and <=2ms bus operations. JY SharedStart adds no global configuration. */
    SILVERSTAR_ASSERT(now_us >= s_cold.activated_us, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    return (uint8_t)((now_us - s_cold.activated_us) <
        SYSTEM_BAROMETER_COLD_BACKUP_FIRST_SAMPLE_TIMEOUT_US);
}

static uint8_t SystemBarometerCold_SampleUsable(
    const SystemBarometerSample *sample, const SystemDeviceHealth *health,
    uint64_t now_us)
{
    if ((health->started == 0U) || (health->online == 0U) || (health->healthy == 0U))
    { return 0U; }
    if (((sample->supported_fields & sample->valid_fields & SYSTEM_BARO_FIELD_PRESSURE) == 0U) ||
        !isfinite(sample->pressure_pa) || (sample->pressure_pa < 1000.0F) ||
        (sample->pressure_pa > 120000.0F)) { return 0U; }
    if ((sample->receive_timestamp_us < s_cold.activated_us) ||
        (sample->receive_timestamp_us > now_us) || (sample->sample_timestamp_us > now_us))
    { return 0U; }
    return (uint8_t)((now_us - sample->receive_timestamp_us) <=
        SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US);
}

static void SystemBarometerCold_SamplePublish(
    const SystemBarometerSample *sample, const SystemDeviceHealth *health)
{
    PlatformCriticalState state;
    SILVERSTAR_ASSERT((sample->valid_fields & ~sample->supported_fields) == 0U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(sample->measurement_timestamp_trusted <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    state = PlatformCritical_Enter();
    if ((s_cold.raw_known == 0U) || (sample->sequence != s_cold.raw_sequence) ||
        (sample->receive_timestamp_us != s_cold.sample.receive_timestamp_us))
    {
        s_cold.logical_sequence++;
        if (s_cold.logical_sequence == 0U) { s_cold.logical_sequence++; }
    }
    s_cold.raw_sequence = sample->sequence;
    s_cold.raw_known = 1U;
    s_cold.sample_ever_received = 1U;
    s_cold.sample = *sample;
    s_cold.sample.sequence = s_cold.logical_sequence;
    s_cold.health = *health;
    s_cold.sample_valid = 1U;
    PlatformCritical_Exit(state);
}

SystemDeviceResult SystemBarometerCold_Process(void)
{
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    SystemDeviceResult result;
    uint64_t now_us;
    uint8_t sample_ready;
    if (s_cold.active == SYSTEM_BAROMETER_COLD_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    if (s_cold.running == SYSTEM_BAROMETER_COLD_INSTANCE_NONE)
    { return SYSTEM_DEVICE_BAD_STATE; }
    SILVERSTAR_ASSERT((s_cold.active < s_cold.count) &&
        (s_cold.active == s_cold.running), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    result = ProjectBarometerInstance_Process(s_cold.active);
    sample_ready = (uint8_t)(((result == SYSTEM_DEVICE_OK) ||
        (result == SYSTEM_DEVICE_NOT_READY)) &&
        (ProjectBarometerInstance_HealthGet(s_cold.active, &health) == SYSTEM_DEVICE_OK) &&
        (ProjectBarometerInstance_LatestSampleGet(s_cold.active, &sample) == SYSTEM_DEVICE_OK));
    /* The driver may timestamp a new sample during processing or the getter.
     * Compare that snapshot with the post-read clock, never the entry clock. */
    now_us = SystemTime_GetMonotonicUs();
    if ((sample_ready != 0U) &&
        (SystemBarometerCold_SampleUsable(&sample, &health, now_us) != 0U))
    {
        s_cold.last_good_us = sample.receive_timestamp_us;
        SystemBarometerCold_SamplePublish(&sample, &health);
        return SYSTEM_DEVICE_OK;
    }
    {
        PlatformCriticalState state = PlatformCritical_Enter();
        s_cold.sample_valid = 0U;
        s_cold.health.online = 0U;
        s_cold.health.healthy = 0U;
        PlatformCritical_Exit(state);
    }
    SILVERSTAR_ASSERT(now_us >= s_cold.last_good_us, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    if (s_cold.raw_known == 0U)
    {
        if (SystemBarometerCold_FirstSamplePending(now_us) != 0U)
        { return SYSTEM_DEVICE_NOT_READY; }
    }
    else if ((now_us - s_cold.last_good_us) < SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US)
    { return SYSTEM_DEVICE_NOT_READY; }
    if (SystemBarometerCold_Stop() != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    return SystemBarometerCold_NextSelect(1U);
}

uint8_t SystemBarometerCold_ActiveGet(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    uint8_t active = s_cold.active;
    PlatformCritical_Exit(state);
    return active;
}

static uint8_t SystemBarometerCold_CacheFresh(uint64_t receive_timestamp_us)
{
    uint64_t now_us = SystemTime_GetMonotonicUs();
    return (uint8_t)((now_us >= receive_timestamp_us) &&
        ((now_us - receive_timestamp_us) <= SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US));
}

SystemDeviceResult SystemBarometerCold_SampleGet(SystemBarometerSample *sample)
{
    PlatformCriticalState state;
    uint8_t valid;
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    state = PlatformCritical_Enter();
    valid = s_cold.sample_valid;
    if (valid != 0U) { *sample = s_cold.sample; }
    PlatformCritical_Exit(state);
    if ((valid != 0U) && (SystemBarometerCold_CacheFresh(sample->receive_timestamp_us) == 0U))
    { valid = 0U; }
    return valid != 0U ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemBarometerCold_HealthGet(SystemDeviceHealth *health)
{
    PlatformCriticalState state;
    uint8_t valid;
    uint64_t receive_timestamp_us;
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    state = PlatformCritical_Enter();
    valid = s_cold.sample_valid;
    receive_timestamp_us = s_cold.sample.receive_timestamp_us;
    *health = s_cold.health;
    PlatformCritical_Exit(state);
    if ((valid == 0U) || (SystemBarometerCold_CacheFresh(receive_timestamp_us) == 0U))
    { health->online = 0U; health->healthy = 0U; valid = 0U; }
    return valid != 0U ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
