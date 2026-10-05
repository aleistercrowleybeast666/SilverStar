#include <stdint.h>
#include <string.h>

#include "system_alignment.h"
#include "system_calibration.h"
#include "system_health.h"
#include "system_output_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "test_common.h"

static uint64_t s_now_us;
static uint8_t s_channel_state[2];
static uint8_t s_channel_fault[2];
static uint8_t s_status_error_channel;
static SystemCapabilities s_capabilities;
static SystemStartupReport s_startup_report;
static SystemDeviceResult s_capability_result;
static uint8_t s_calibration_ready;
static SystemAlignmentStatus s_alignment_status;

uint8_t SystemCalibration_IsReady(void) { return s_calibration_ready; }
uint8_t SystemAlignment_IsReady(void) { return s_alignment_status.ready; }

const SystemStartupReport *SystemStartup_GetReport(void)
{
    return &s_startup_report;
}

static const SystemProfile s_profile =
{
    .profile_id = 1U,
    .output_channel_count = 2U,
    .enabled_capabilities = SYSTEM_CAPABILITY_IMU |
                            SYSTEM_CAPABILITY_OUTPUT |
                            SYSTEM_CAPABILITY_BAROMETER,
    .required_capabilities = SYSTEM_CAPABILITY_IMU |
                             SYSTEM_CAPABILITY_OUTPUT,
    .optional_capabilities = SYSTEM_CAPABILITY_BAROMETER
};

static SystemDeviceResult Mock_OutputStatus(uint8_t channel,
                                             SystemOutputStatus *status)
{
    if ((status == NULL) || (channel == 0U) || (channel > 2U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (channel == s_status_error_channel)
    {
        return SYSTEM_DEVICE_IO_ERROR;
    }
    (void)memset(status, 0, sizeof(*status));
    status->channel = channel;
    status->state = (SystemOutputState)s_channel_state[channel - 1U];
    status->fault = s_channel_fault[channel - 1U];
    status->physical_active =
        (status->state == SYSTEM_OUTPUT_ACTIVE) ? 1U : 0U;
    return SYSTEM_DEVICE_OK;
}

const SystemProfile *SystemProfile_Get(void)
{
    return &s_profile;
}

SystemDeviceResult SystemOutput_StatusGet(
    uint8_t channel, SystemOutputStatus *status)
{ return Mock_OutputStatus(channel, status); }

SystemDeviceResult SystemCapabilities_Refresh(void)
{
    return s_capability_result;
}

void SystemCapabilities_Get(SystemCapabilities *capabilities)
{
    if (capabilities != NULL)
    {
        *capabilities = s_capabilities;
    }
}

uint8_t SystemCapabilities_RequiredAvailable(uint32_t required_mask)
{
    uint32_t available = s_capabilities.present_mask &
                         s_capabilities.healthy_mask;

    return (uint8_t)((available & required_mask) == required_mask);
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    return ++s_now_us;
}

static void Test_Reset(void)
{
    (void)memset(&s_capabilities, 0, sizeof(s_capabilities));
    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.completed = 1U;
    s_startup_report.mission_capable = 1U;
    s_capabilities.present_mask = SYSTEM_CAPABILITY_IMU |
                                  SYSTEM_CAPABILITY_OUTPUT;
    s_capabilities.healthy_mask = s_capabilities.present_mask;
    s_channel_state[0] = (uint8_t)SYSTEM_OUTPUT_SAFE;
    s_channel_state[1] = (uint8_t)SYSTEM_OUTPUT_SAFE;
    s_channel_fault[0] = 0U;
    s_channel_fault[1] = 0U;
    s_status_error_channel = 0U;
    s_capability_result = SYSTEM_DEVICE_OK;
    s_calibration_ready = 1U;
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    SystemHealth_Init();
    SystemHealth_SetAttitudeReady(1U);
}

int main(void)
{
    SystemHealthSnapshot snapshot;

    Test_Reset();
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK(snapshot.ready != 0U);
    TEST_CHECK(snapshot.start_blocking_mask == 0U);
    TEST_CHECK((snapshot.capabilities.present_mask &
                SYSTEM_CAPABILITY_BAROMETER) == 0U);

    s_calibration_ready = 0U;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_CALIBRATION_NOT_READY) != 0U);
    s_calibration_ready = 1U;
    s_alignment_status.ready = 0U;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_ALIGNMENT_NOT_READY) != 0U);
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_STALE;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK(snapshot.ready == 0U);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_ALIGNMENT_NOT_READY) != 0U);
    s_alignment_status.ready = 1U;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;

    s_channel_state[1] = (uint8_t)SYSTEM_OUTPUT_ACTIVE;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK(snapshot.ready == 0U);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_OUTPUT_NOT_SAFE) != 0U);

    s_channel_state[1] = (uint8_t)SYSTEM_OUTPUT_SAFE;
    s_status_error_channel = 2U;
    SystemHealth_Process();
    TEST_CHECK(SystemHealth_IsReady() == 0U);

    s_status_error_channel = 0U;
    s_channel_fault[1] = 1U;
    SystemHealth_Process();
    TEST_CHECK(SystemHealth_IsReady() == 0U);

    s_channel_fault[1] = 0U;
    SystemHealth_SetAttitudeReady(0U);
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_ATTITUDE_UNAVAILABLE) != 0U);

    SystemHealth_SetAttitudeReady(1U);
    s_capabilities.healthy_mask &= ~SYSTEM_CAPABILITY_IMU;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK(snapshot.ready == 0U);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_REQUIRED_DEVICE) != 0U);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_PRIMARY_IMU) != 0U);

    s_capabilities.healthy_mask |= SYSTEM_CAPABILITY_IMU;
    s_capability_result = SYSTEM_DEVICE_IO_ERROR;
    SystemHealth_Process();
    SystemHealth_GetSnapshot(&snapshot);
    TEST_CHECK((snapshot.start_blocking_mask &
                SYSTEM_HEALTH_BLOCK_PROFILE_INVALID) != 0U);

    return Test_Finish("health");
}
