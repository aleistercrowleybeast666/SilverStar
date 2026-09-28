/* Reuse AIR transport/handshake fixtures, but link the real command managers. */
#include <setjmp.h>
#include "system_calibration.h"
#include "system_alignment.h"
#include "system_alignment_backend.h"
#include "platform_critical.h"
#include "app_tasks.h"
#include "task.h"
#define SystemAlignment_CapabilityMaskGet Fixture_SystemAlignment_CapabilityMaskGet
#define SystemAlignment_StatusGet Fixture_SystemAlignment_StatusGet
#define SystemAlignment_SummaryGet Fixture_SystemAlignment_SummaryGet
#define SystemAlignment_PreflightQuaternionGet Fixture_SystemAlignment_PreflightQuaternionGet
#define SystemAlignment_Start Fixture_SystemAlignment_Start
#define SystemAlignment_Stop Fixture_SystemAlignment_Stop
#define SystemAlignment_Reset Fixture_SystemAlignment_Reset
#define SystemCalibration_StatusGet Fixture_SystemCalibration_StatusGet
#define SystemCalibration_ImuCorrectionGet Fixture_SystemCalibration_ImuCorrectionGet
#define SystemCalibration_Start Fixture_SystemCalibration_Start
#define SystemCalibration_FaceCollect Fixture_SystemCalibration_FaceCollect
#define SystemCalibration_Stop Fixture_SystemCalibration_Stop
#define SystemCalibration_Reset Fixture_SystemCalibration_Reset
#define main Test_TelemetryFixtureMain
#include "test_telemetry.c"
#undef main
#undef SystemAlignment_CapabilityMaskGet
#undef SystemAlignment_StatusGet
#undef SystemAlignment_SummaryGet
#undef SystemAlignment_PreflightQuaternionGet
#undef SystemAlignment_Start
#undef SystemAlignment_Stop
#undef SystemAlignment_Reset
#undef SystemCalibration_StatusGet
#undef SystemCalibration_ImuCorrectionGet
#undef SystemCalibration_Start
#undef SystemCalibration_FaceCollect
#undef SystemCalibration_Stop
#undef SystemCalibration_Reset
static jmp_buf s_task_exit;
static uint32_t s_task_cycles;
static uint32_t s_backend_reads;
static SystemDeviceResult s_backend_reset = SYSTEM_DEVICE_OK;
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
SystemDeviceResult SystemLifecycle_EnterPreflight(void)
{ s_lifecycle_state = SYSTEM_STATE_PREFLIGHT; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *capability)
{ *capability = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *capability)
{ *capability = SYSTEM_GNSS_CAP_POSITION; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *capability)
{ *capability = 0U; return SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemAlignmentBackend_Reset(void) { return s_backend_reset; }
SystemDeviceResult SystemAlignmentBackend_PrepareMission(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemAlignmentBackend_FreezeSources(void) { return SYSTEM_DEVICE_OK; }
void SystemAlignmentBackend_MissionPreparationAbort(void) { }
SystemDeviceResult SystemAlignmentBackend_GuardSampleGet(SystemAlignmentGuardSample *sample)
{ (void)sample; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemAlignmentBackend_SourceStatusGet(SystemAlignmentSourceId id,
    SystemAlignmentSourceStatus *status)
{
    (void)id;
    s_backend_reads++;
    (void)memset(status, 0, sizeof(*status));
    status->state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    return SYSTEM_DEVICE_OK;
}
void vTaskDelay(TickType_t ticks)
{
    (void)ticks;
    s_task_cycles++;
    if (s_task_cycles == 1U)
    {
        Test_Authorize();
        Test_CommandQueue(10U, AIR_CMD_ALIGN_START, AIR_TOKEN_ALIGNMENT, 0U, 0U);
    }
    else
    {
        longjmp(s_task_exit, 1);
    }
}
int main(void)
{
    SystemAlignmentStatus before;
    SystemAlignmentStatus after;
    const TestFrame *ack;
    Test_Reset();
    SystemCalibration_Init();
    SystemAlignment_Init();
    TEST_CHECK(SystemCalibration_IsReady() != 0U);
    if (setjmp(s_task_exit) == 0) { AppTask_Telemetry(NULL); }
    ack = Test_LastTypeGet(AIR_TYPE_ACK);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[3] == AIR_CMD_ALIGN_START);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&before) == SYSTEM_DEVICE_OK);
    TEST_CHECK(before.state == SYSTEM_ALIGNMENT_STATE_COLLECTING);
    TEST_CHECK(before.start_sequence == 1U);
    TEST_CHECK(s_backend_reads == 0U);
    /* The periodic operation called by production FlightTask now advances it. */
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_backend_reads > 0U);
    TEST_CHECK(SystemAlignment_StatusGet(&before) == SYSTEM_DEVICE_OK);
    Test_CommandQueue(11U, AIR_CMD_CAL_START, AIR_TOKEN_CALIBRATION, SYSTEM_CALIBRATION_MODE_ONE_FACE, 0U);
    TelemetryService_Process();
    ack = Test_LastTypeGet(AIR_TYPE_ACK);
    TEST_CHECK(ack->data[4] != AIR_ACK_RESULT_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&after) == SYSTEM_DEVICE_OK);
    TEST_CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    TEST_CHECK(SystemCalibration_IsReady() != 0U);
    s_backend_reset = SYSTEM_DEVICE_BUSY;
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_BUSY);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_BAD_STATE);
    return Test_Finish("runtime_commands");
}
