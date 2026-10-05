#include "app_tasks.h"

#include "FreeRTOS.h"
#include "task.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "diagnostic_log.h"
#endif
#include "silverstar_assert.h"
#include "system_time.h"
#include "telemetry_service.h"

/* EstimatorTask and radio fault evidence use the same monotonic clock.
 * A live DAP reader accepts only equal, even sequence values around a read. */
typedef struct
{
    uint32_t sequence;
    uint64_t last_start_us;
    uint64_t max_interval_end_us;
    uint64_t first_long_interval_end_us;
    uint64_t last_long_interval_end_us;
    uint32_t last_interval_us;
    uint32_t max_interval_us;
    uint32_t interval_over_20ms_count;
    uint32_t cycle_count;
} TelemetryTaskTimingDiagnostics;

static volatile TelemetryTaskTimingDiagnostics s_telemetry_task_timing;

static void TelemetryTask_TimingRecord(uint64_t now_us)
{
    uint64_t elapsed_us;
    uint32_t interval_us;

    s_telemetry_task_timing.sequence++;
    if ((s_telemetry_task_timing.last_start_us != 0U) &&
        (now_us >= s_telemetry_task_timing.last_start_us))
    {
        elapsed_us = now_us - s_telemetry_task_timing.last_start_us;
        interval_us = (elapsed_us > UINT32_MAX) ? UINT32_MAX : (uint32_t)elapsed_us;
        s_telemetry_task_timing.last_interval_us = interval_us;
        if (interval_us > s_telemetry_task_timing.max_interval_us)
        {
            s_telemetry_task_timing.max_interval_us = interval_us;
            s_telemetry_task_timing.max_interval_end_us = now_us;
        }
        if ((interval_us >= 20000U) &&
            (s_telemetry_task_timing.interval_over_20ms_count < UINT32_MAX))
        {
            if (s_telemetry_task_timing.first_long_interval_end_us == 0U)
            { s_telemetry_task_timing.first_long_interval_end_us = now_us; }
            s_telemetry_task_timing.last_long_interval_end_us = now_us;
            s_telemetry_task_timing.interval_over_20ms_count++;
        }
    }
    s_telemetry_task_timing.last_start_us = now_us;
    if (s_telemetry_task_timing.cycle_count < UINT32_MAX)
    { s_telemetry_task_timing.cycle_count++; }
    s_telemetry_task_timing.sequence++;
}

void AppTask_Telemetry(void *argument)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    static DiagnosticLogPeriodicState telemetry_log_state;
#endif
    SystemDeviceResult init_result;

    (void)argument;
    init_result = TelemetryService_Init();
    SILVERSTAR_ASSERT(init_result <= SYSTEM_DEVICE_NOT_PRESENT,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((init_result != SYSTEM_DEVICE_INVALID_ARGUMENT) &&
                      (init_result != SYSTEM_DEVICE_BAD_STATE),
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);

    for (;;)
    {
        TelemetryTask_TimingRecord(SystemTime_GetMonotonicUs());
        if ((init_result == SYSTEM_DEVICE_OK) ||
            (init_result == SYSTEM_DEVICE_ALREADY_MATCHED))
        {
            TelemetryService_Process();
        }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        DiagnosticLog_TelemetryProcess(
            &telemetry_log_state, SystemTime_GetMonotonicUs());
#endif
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}
