#include <string.h>

#include "app_tasks.h"
#include "task.h"
#include "estimator_bus.h"
#include "estimator_task.h"
#include "imu_sample_bus.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "platform_gpio.h"
#include "platform_critical.h"
#include "project_resources.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_mag_calibration.h"
#include "system_gnss_if.h"
#include "system_indicator.h"
#include "system_navigation_health.h"
#include "system_user_config.h"
#include "test_common.h"

static uint32_t s_created;
static uint32_t s_gpio_writes;
static uint32_t s_selector_calls;
static uint8_t s_gpio_level;
static uint8_t s_alignment_initialized;
static uint64_t s_now_us;
static TaskHandle_t s_telemetry_handle;

SystemDeviceResult EstimatorTask_PreparationGet(EstimatorPreparationSnapshot *snapshot)
{
    if (snapshot == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    return SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemNavigationHealth_GroupGet(uint8_t group,
    uint64_t evaluation_us, SystemNavigationGroupHealth *snapshot)
{
    if ((group >= SYSTEM_NAVIGATION_GROUP_COUNT) || (snapshot == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->last_receive_us = evaluation_us;
    return SYSTEM_DEVICE_NOT_READY;
}

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_PREFLIGHT; }
uint8_t SystemHealth_IsReady(void) { return 0U; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void)
{
    s_selector_calls++;
    return SYSTEM_DEVICE_NOT_READY;
}
void SystemSourceSelector_PendingEventsFlush(void) { }
void SystemAlignment_Init(void) { s_alignment_initialized = 1U; }
void SystemMagCalibration_Init(void) {}
SystemDeviceResult SystemAlignment_CalibrationInvalidate(void)
{
    return (s_alignment_initialized != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{
    (void)memset(summary, 0, sizeof(*summary));
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health)
{ (void)health; return SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ (void)sample; return SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemInertial_Init(void) { return SYSTEM_DEVICE_OK; }
ImuSampleBusResult ImuSampleBus_Init(void) { return IMU_SAMPLE_BUS_RESULT_OK; }
EstimatorBusResult EstimatorBus_Init(void) { return ESTIMATOR_BUS_RESULT_OK; }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
LoggerBusResult LoggerBus_Init(void) { return LOGGER_BUS_RESULT_OK; }
#endif
void AppTask_Device(void *argument) { (void)argument; }
void AppTask_Ins(void *argument) { (void)argument; }
void AppTask_Estimator(void *argument) { (void)argument; }
void AppTask_Flight(void *argument) { (void)argument; }
void AppTask_Logger(void *argument) { (void)argument; }
void AppTask_Serial(void *argument) { (void)argument; }
void AppTask_Telemetry(void *argument) { (void)argument; }

TaskHandle_t xTaskCreateStatic(TaskFunction_t entry, const char *name,
    uint32_t words, void *argument, UBaseType_t priority,
    StackType_t *stack, StaticTask_t *control)
{
    (void)entry; (void)words; (void)argument; (void)priority; (void)stack;
    TEST_CHECK(s_alignment_initialized != 0U);
    TEST_CHECK(SystemCalibration_IsReady() != 0U);
    /* This can only succeed if production init initialized the indicator. */
    TEST_CHECK(SystemIndicator_ModeSet(SYSTEM_INDICATOR_SYSTEM,
        SYSTEM_INDICATOR_MODE_OFF) == SYSTEM_DEVICE_OK);
    if (strcmp(name, "Telemetry") == 0) { s_telemetry_handle = control; }
    s_created++;
    return control;
}
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task)
{ (void)task; return 123U; }
PlatformResult PlatformGpio_Write(PlatformGpioId gpio, uint8_t level)
{
    TEST_CHECK(gpio == PROJECT_RESOURCE_SYSTEM_INDICATOR);
    TEST_CHECK(gpio == PLATFORM_GPIO_6);
    s_gpio_level = level;
    s_gpio_writes++;
    return PLATFORM_OK;
}

int main(void)
{
    SystemCalibrationStatus calibration;
    SystemTaskStackSnapshot stacks;
    SilverStarAssertFaultRecord fault;
    uint32_t previous_sequence;

    /* No test-side Calibration/Alignment/Indicator Init or CAL_START. */
    TEST_CHECK(AppTasks_Init() == AppTasksInitResult_Ok);
    TEST_CHECK(s_created == (6U + (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U ? 1U : 0U)));
    TEST_CHECK(s_selector_calls == 0U);
    TEST_CHECK(SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK);
    TEST_CHECK(calibration.mode == SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(calibration.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(calibration.correction.accel_scale[0] == 1.0f);
    previous_sequence = calibration.start_sequence;
    SystemIndicator_Process();
    TEST_CHECK(s_gpio_writes > 0U);
    TEST_CHECK(s_gpio_level == 0U); /* SS0.5 active-low ON. */
    s_now_us = SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US;
    SystemIndicator_Process();
    TEST_CHECK(s_gpio_level == 1U);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK);
    TEST_CHECK(calibration.ready == 1U);
    TEST_CHECK(calibration.mode == SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(calibration.start_sequence > previous_sequence);
    TEST_CHECK(SystemTaskStack_SnapshotGet(&stacks) == SYSTEM_DEVICE_OK);
    SystemTaskStack_OverflowContextSet((uintptr_t)s_telemetry_handle, 1U);
    TEST_CHECK(SilverStarAssert_FaultRecordGet(&fault) == 0U);
    TEST_CHECK(fault.fault_type == SILVERSTAR_FAULT_STACK_OVERFLOW);
    TEST_CHECK(fault.task_id == SYSTEM_TASK_STACK_RADIO);
    TEST_CHECK(strcmp(fault.task_name, "Telemetry") == 0);
    TEST_CHECK(fault.task_name_address == 1U); /* Never dereferenced. */
    TEST_CHECK(fault.system_state == SYSTEM_STATE_PREFLIGHT);
    TEST_CHECK(fault.high_water_mark_words == 123U);
    TEST_CHECK(fault.high_water_mark_valid == 1U);
    SystemTaskStack_OverflowContextSet(1U, 1U);
    TEST_CHECK(SilverStarAssert_FaultRecordGet(&fault) == 0U);
    TEST_CHECK(fault.task_id == SILVERSTAR_FAULT_TASK_UNKNOWN);
    TEST_CHECK(fault.high_water_mark_valid == 0U);
    return Test_Finish("runtime_startup");
}
