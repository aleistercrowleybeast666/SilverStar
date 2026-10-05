#include "imu_sample_bus.h"

#include <stddef.h>
#include <string.h>

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_calibration.h"
#include "system_inertial.h"
#include "system_lifecycle.h"
#include "system_user_config.h"
#include "system_user_startup_config.h"

static InsImuSample s_queue[IMU_SAMPLE_BUS_DEPTH];
static volatile uint16_t s_head;
static volatile uint16_t s_tail;
static uint8_t s_initialized;
static uint32_t s_last_device_sequence;
static ImuSampleBusStats s_stats;

static uint16_t ImuSampleBus_Next(uint16_t index)
{
    index++;
    return (index >= IMU_SAMPLE_BUS_DEPTH) ? 0U : index;
}

static PlatformCriticalState ImuSampleBus_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void ImuSampleBus_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

ImuSampleBusResult ImuSampleBus_Init(void)
{
    if (s_initialized != 0U)
    {
        return IMU_SAMPLE_BUS_RESULT_OK;
    }
    (void)memset(s_queue, 0, sizeof(s_queue));
    (void)memset(&s_stats, 0, sizeof(s_stats));
    s_head = 0U;
    s_tail = 0U;
    s_last_device_sequence = 0U;
    s_initialized = 1U;
    return IMU_SAMPLE_BUS_RESULT_OK;
}

void ImuSampleBus_Reset(void)
{
    uint32_t primask = ImuSampleBus_IrqLock();

    s_head = 0U;
    s_tail = 0U;
    s_stats.count = 0U;
    ImuSampleBus_IrqUnlock(primask);
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static uint8_t ImuSampleBus_CorrectedLoggingAllowed(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    if (SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE != 0U)
    {
        return 1U;
    }
    return (uint8_t)((state == SYSTEM_STATE_FLIGHT) ||
                     (state == SYSTEM_STATE_RECOVERY));
}

static void ImuSampleBus_CorrectedLog(const InsImuSample *sample)
{
    FlightLogImuCorrectedRecord record;
    SystemCalibrationImuCorrection correction;

    if (sample == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(sample, InsImuSample,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if ((ImuSampleBus_CorrectedLoggingAllowed() == 0U) ||
        (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK))
    {
        return;
    }
    (void)memset(&record, 0, sizeof(record));
    record.sample_timestamp_us = sample->sample_timestamp_us;
    record.receive_timestamp_us = sample->receive_timestamp_us;
    record.sequence = sample->sequence;
    record.source_id = FLIGHT_LOG_PRIMARY_INERTIAL_SOURCE_ID;
    record.virtual_imu_id = FLIGHT_LOG_PRIMARY_VIRTUAL_IMU_ID;
    record.valid_mask = sample->valid_mask;
    if (SystemCalibration_ImuCorrectionApply(
            sample->accel_b_mps2, sample->gyro_b_radps, &correction,
            record.accel_b_mps2, record.gyro_b_radps) != SYSTEM_DEVICE_OK)
    {
        return;
    }
    record.temperature_c = sample->temperature_c;
    record.calibration_mode = (uint8_t)correction.mode;
    record.correction_valid = correction.ready;
    (void)LoggerBus_ImuCorrectedPush(sample->sample_timestamp_us,
                                     sample->valid_mask, &record);
}
#endif

void ImuSampleBus_Process(void)
{
    InsImuSample sample;
    uint16_t next_head;
    uint32_t primask;
    uint32_t drained = 0U;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(SYSTEM_IMU_DRAIN_MAX_SAMPLES_PER_CYCLE > 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    if (s_initialized == 0U)
    {
        return;
    }
    for (drained = 0U;
         drained < SYSTEM_IMU_DRAIN_MAX_SAMPLES_PER_CYCLE;
         drained++)
    {
        if (SystemInertial_NextGet(&sample) != SYSTEM_DEVICE_OK)
        {
            break;
        }
        if (((sample.valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                                   SYSTEM_INERTIAL_VALID_GYRO)) !=
             (SYSTEM_INERTIAL_VALID_ACCEL |
              SYSTEM_INERTIAL_VALID_GYRO)) ||
            (sample.sequence == s_last_device_sequence))
        {
            continue;
        }
        if ((s_last_device_sequence != 0U) &&
            ((uint32_t)(sample.sequence - s_last_device_sequence) > 1U))
        {
            s_stats.source_gap_count +=
                (uint32_t)(sample.sequence - s_last_device_sequence - 1U);
        }
        s_last_device_sequence = sample.sequence;
        SystemCalibration_ImuSampleProcess(&sample);

        primask = ImuSampleBus_IrqLock();
        next_head = ImuSampleBus_Next(s_head);
        if (next_head == s_tail)
        {
            s_stats.overflow_count++;
            ImuSampleBus_IrqUnlock(primask);
            continue;
        }
        s_queue[s_head] = sample;
        s_head = next_head;
        s_stats.push_count++;
        s_stats.count++;
        ImuSampleBus_IrqUnlock(primask);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        ImuSampleBus_CorrectedLog(&sample);
#endif
    }
}

ImuSampleBusResult ImuSampleBus_Pop(InsImuSample *sample)
{
    uint32_t primask;

    if (sample == NULL)
    {
        return IMU_SAMPLE_BUS_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, InsImuSample,
                             SILVERSTAR_ASSERT_MODULE_APP);
    primask = ImuSampleBus_IrqLock();
    if (s_initialized == 0U)
    {
        ImuSampleBus_IrqUnlock(primask);
        return IMU_SAMPLE_BUS_RESULT_NOT_READY;
    }
    if (s_tail == s_head)
    {
        ImuSampleBus_IrqUnlock(primask);
        return IMU_SAMPLE_BUS_RESULT_EMPTY;
    }
    *sample = s_queue[s_tail];
    s_tail = ImuSampleBus_Next(s_tail);
    s_stats.pop_count++;
    if (s_stats.count != 0U)
    {
        s_stats.count--;
    }
    ImuSampleBus_IrqUnlock(primask);
    return IMU_SAMPLE_BUS_RESULT_OK;
}

void ImuSampleBus_StatsGet(ImuSampleBusStats *stats)
{
    uint32_t primask;

    if (stats == NULL)
    {
        return;
    }
    primask = ImuSampleBus_IrqLock();
    *stats = s_stats;
    ImuSampleBus_IrqUnlock(primask);
}

void ImuSampleBus_BiasSnapshotGet(ImuSampleBusBiasSnapshot *snapshot)
{
    SystemCalibrationStatus status;
    uint8_t index;

    if (snapshot == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(snapshot, ImuSampleBusBiasSnapshot,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(snapshot, 0, sizeof(*snapshot));
    if (SystemCalibration_StatusGet(&status) != SYSTEM_DEVICE_OK)
    {
        snapshot->state = IMU_SAMPLE_BUS_BIAS_STATE_WAIT_STREAM;
        snapshot->wait_reason = IMU_SAMPLE_BUS_BIAS_WAIT_NO_STREAM;
        return;
    }
    for (index = 0U; index < 3U; index++)
    {
        snapshot->accel_bias_b_mps2[index] =
            status.correction.accel_bias_mps2[index];
        snapshot->gyro_bias_b_radps[index] =
            status.correction.gyro_bias_radps[index];
    }
    snapshot->window_valid_sample_count = status.samples;
    snapshot->window_reject_count = status.reject_count;
    snapshot->retry_count = status.retry_count;
    snapshot->wait_reason = (ImuSampleBusBiasWaitReason)status.wait_reason;
    snapshot->mode = (uint8_t)status.mode;
    snapshot->startup_up_direction =
        SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION;
    snapshot->ready = status.ready;
    if (status.ready != 0U)
    {
        snapshot->state = IMU_SAMPLE_BUS_BIAS_STATE_READY;
    }
    else if (status.state == SYSTEM_CALIBRATION_STATE_COLLECTING)
    {
        snapshot->state = IMU_SAMPLE_BUS_BIAS_STATE_COLLECTING_WINDOW;
    }
    else
    {
        snapshot->state = IMU_SAMPLE_BUS_BIAS_STATE_WAIT_STREAM;
    }
}

SystemDeviceResult ImuSampleBus_BiasReset(void)
{
    return SystemCalibration_Reset();
}
