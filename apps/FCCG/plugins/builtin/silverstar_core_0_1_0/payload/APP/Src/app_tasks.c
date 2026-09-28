#include "app_tasks.h"


#include "silverstar_assert.h"
#include <stddef.h>
#include <string.h>

#include "FreeRTOS.h"
#include "app_task_config.h"
#include "estimator_bus.h"
#include "imu_sample_bus.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "platform_memory.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_inertial.h"
#include "system_indicator.h"
#include "system_lifecycle.h"
#include "system_source_selector.h"
#include "task.h"

typedef struct
{
    uint32_t stack_words;
    TaskHandle_t handle;
    volatile uint32_t high_water_mark_words;
    volatile uint8_t high_water_mark_valid;
} AppTaskStorage;

static StaticTask_t s_device_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_device_stack[APP_TASK_STACK_DEVICE_WORDS];
static StaticTask_t s_ins_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_ins_stack[APP_TASK_STACK_INS_WORDS];
static StaticTask_t s_estimator_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_estimator_stack[APP_TASK_STACK_ESTIMATOR_WORDS];
static StaticTask_t s_flight_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_flight_stack[APP_TASK_STACK_FLIGHT_WORDS];
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static StaticTask_t s_logger_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_logger_stack[APP_TASK_STACK_LOGGER_WORDS];
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
static StaticTask_t s_serial_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_serial_stack[APP_TASK_STACK_SERIAL_WORDS];
#endif
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
static StaticTask_t s_telemetry_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_telemetry_stack[APP_TASK_STACK_TELEMETRY_WORDS];
#endif

static AppTaskStorage s_tasks[SYSTEM_TASK_STACK_COUNT] =
{
    [SYSTEM_TASK_STACK_DEVICE] = {
        .stack_words = APP_TASK_STACK_DEVICE_WORDS
    },
    [SYSTEM_TASK_STACK_INS] = {
        .stack_words = APP_TASK_STACK_INS_WORDS
    },
    [SYSTEM_TASK_STACK_ESTIMATOR] = {
        .stack_words = APP_TASK_STACK_ESTIMATOR_WORDS
    },
    [SYSTEM_TASK_STACK_FLIGHT] = {
        .stack_words = APP_TASK_STACK_FLIGHT_WORDS
    },
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    [SYSTEM_TASK_STACK_LOGGER] = {
        .stack_words = APP_TASK_STACK_LOGGER_WORDS
    },
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    [SYSTEM_TASK_STACK_SERIAL] = {
        .stack_words = APP_TASK_STACK_SERIAL_WORDS
    },
#endif
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    [SYSTEM_TASK_STACK_RADIO] = {
        .stack_words = APP_TASK_STACK_TELEMETRY_WORDS
    }
#endif
};

static TaskHandle_t AppTasks_DeviceCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_DEVICE];

    storage->handle = xTaskCreateStatic(
        AppTask_Device, "Device", APP_TASK_STACK_DEVICE_WORDS, NULL,
        APP_PRIORITY_DEVICE, s_device_stack, &s_device_task_control);
    return storage->handle;
}

static TaskHandle_t AppTasks_InsCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_INS];

    storage->handle = xTaskCreateStatic(
        AppTask_Ins, "INS", APP_TASK_STACK_INS_WORDS, NULL,
        APP_PRIORITY_INS, s_ins_stack, &s_ins_task_control);
    return storage->handle;
}

static TaskHandle_t AppTasks_EstimatorCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_ESTIMATOR];

    storage->handle = xTaskCreateStatic(
        AppTask_Estimator, "Estimator", APP_TASK_STACK_ESTIMATOR_WORDS, NULL,
        APP_PRIORITY_ESTIMATOR, s_estimator_stack,
        &s_estimator_task_control);
    return storage->handle;
}

static TaskHandle_t AppTasks_FlightCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_FLIGHT];

    storage->handle = xTaskCreateStatic(
        AppTask_Flight, "Flight", APP_TASK_STACK_FLIGHT_WORDS, NULL,
        APP_PRIORITY_FLIGHT, s_flight_stack, &s_flight_task_control);
    return storage->handle;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static TaskHandle_t AppTasks_LoggerCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_LOGGER];

    storage->handle = xTaskCreateStatic(
        AppTask_Logger, "Logger", APP_TASK_STACK_LOGGER_WORDS, NULL,
        APP_PRIORITY_LOGGER, s_logger_stack, &s_logger_task_control);
    return storage->handle;
}
#endif

#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
static TaskHandle_t AppTasks_SerialCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_SERIAL];

    storage->handle = xTaskCreateStatic(
        AppTask_Serial, "Serial", APP_TASK_STACK_SERIAL_WORDS, NULL,
        APP_PRIORITY_SERIAL, s_serial_stack, &s_serial_task_control);
    return storage->handle;
}
#endif

#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
static TaskHandle_t AppTasks_TelemetryCreate(void)
{
    AppTaskStorage *storage = &s_tasks[SYSTEM_TASK_STACK_RADIO];

    storage->handle = xTaskCreateStatic(
        AppTask_Telemetry, "Telemetry", APP_TASK_STACK_TELEMETRY_WORDS, NULL,
        APP_PRIORITY_TELEMETRY, s_telemetry_stack,
        &s_telemetry_task_control);
    return storage->handle;
}
#endif

AppTasksInitResult AppTasks_Init(void)
{
    SILVERSTAR_ASSERT(s_tasks[SYSTEM_TASK_STACK_DEVICE].stack_words ==
                      APP_TASK_STACK_DEVICE_WORDS,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    SILVERSTAR_ASSERT(s_tasks[SYSTEM_TASK_STACK_RADIO].stack_words ==
                      APP_TASK_STACK_TELEMETRY_WORDS,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
#endif
    SystemCalibration_Init();
    SystemAlignment_Init();
    SystemIndicator_Init();
    if ((SystemInertial_Init() != SYSTEM_DEVICE_OK) ||
        (ImuSampleBus_Init() != IMU_SAMPLE_BUS_RESULT_OK) ||
        (EstimatorBus_Init() != ESTIMATOR_BUS_RESULT_OK)
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        || (LoggerBus_Init() != LOGGER_BUS_RESULT_OK)
#endif
        )
    {
        return AppTasksInitResult_BusInitFailed;
    }
    SystemSourceSelector_PendingEventsFlush();

    if ((AppTasks_DeviceCreate() == NULL) ||
        (AppTasks_InsCreate() == NULL) ||
        (AppTasks_EstimatorCreate() == NULL) ||
        (AppTasks_FlightCreate() == NULL)
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        || (AppTasks_LoggerCreate() == NULL)
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
        || (AppTasks_SerialCreate() == NULL)
#endif
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
        || (AppTasks_TelemetryCreate() == NULL)
#endif
        )
    {
        return AppTasksInitResult_TaskCreateFailed;
    }
    return AppTasksInitResult_Ok;
}

SystemDeviceResult SystemTaskStack_SnapshotGet(
    SystemTaskStackSnapshot *snapshot)
{
    uint32_t index;

    if (snapshot == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    for (index = 0U; index < (uint32_t)SYSTEM_TASK_STACK_COUNT; index++)
    {
        AppTaskStorage *storage = &s_tasks[index];

        SILVERSTAR_ASSERT_OBJECT(snapshot, SystemTaskStackSnapshot,
                                 SILVERSTAR_ASSERT_MODULE_APP);
        snapshot->task[index].allocation_words = storage->stack_words;
        if (storage->handle != NULL)
        {
            snapshot->task[index].high_water_mark_words =
                (uint32_t)uxTaskGetStackHighWaterMark(storage->handle);
            snapshot->valid_mask |= (1UL << index);
            storage->high_water_mark_words =
                snapshot->task[index].high_water_mark_words;
            storage->high_water_mark_valid = 1U;
        }
    }
    return SYSTEM_DEVICE_OK;
}

static uint32_t AppTasks_FaultTaskIdGet(uintptr_t task)
{
    uint32_t index;

    for (index = 0U; index < (uint32_t)SYSTEM_TASK_STACK_COUNT; index++)
    {
        if ((task != 0U) && (task == (uintptr_t)s_tasks[index].handle))
        {
            return index;
        }
    }
    return SILVERSTAR_FAULT_TASK_UNKNOWN;
}

void SystemTaskStack_OverflowContextSet(uintptr_t task, uintptr_t task_name)
{
    static const char *const task_names[SYSTEM_TASK_STACK_COUNT] = {
        "Device", "INS", "Estimator", "Flight", "Logger", "Serial", "Telemetry"
    };
    const uint32_t index = AppTasks_FaultTaskIdGet(task);
    if (index != SILVERSTAR_FAULT_TASK_UNKNOWN)
    {
        const AppTaskStorage *storage = &s_tasks[index];
        SilverStarAssert_StackOverflowContextSet(task, task_name,
            index, task_names[index], (uint32_t)SystemLifecycle_GetState(),
            storage->high_water_mark_words, storage->high_water_mark_valid);
        return;
    }
    SilverStarAssert_StackOverflowContextSet(task, task_name,
        SILVERSTAR_FAULT_TASK_UNKNOWN, NULL,
        (uint32_t)SystemLifecycle_GetState(), 0U, 0U);
}
