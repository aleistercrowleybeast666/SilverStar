#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "system_indicator.h"
#include "system_gnss_if.h"
#include "system_user_config.h"
#include "test_common.h"

static SystemCalibrationStatus s_calibration;
static SystemAlignmentStatus s_alignment;
static SystemLifecycleState s_lifecycle;
static uint8_t s_health_ready;
static uint64_t s_now_us;
static uint8_t s_channel_output[3];
static uint32_t s_channel_write_count[3];
static SystemDeviceHealth s_gnss_health;
static SystemGnssSample s_gnss_sample;
static SystemDeviceResult s_gnss_health_result;
static SystemDeviceResult s_gnss_sample_result;

SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *status = s_calibration;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{
    if (summary == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(summary, 0, sizeof(*summary));
    summary->start_sequence = s_alignment.start_sequence;
    summary->selected_mask = s_alignment.selected_mask;
    summary->ready_mask = s_alignment.ready_mask;
    summary->state = s_alignment.state;
    summary->stale_reason = s_alignment.stale_reason;
    summary->ready = s_alignment.ready;
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemHealth_IsReady(void) { return s_health_ready; }
SystemLifecycleState SystemLifecycle_GetState(void) { return s_lifecycle; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_gnss_health;
    return s_gnss_health_result;
}
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_gnss_sample;
    return s_gnss_sample_result;
}

static SystemDeviceResult TestIndicator_Set(uint8_t channel, uint8_t logical_on)
{
    if (channel >= 3U) { return SYSTEM_DEVICE_UNSUPPORTED; }
    s_channel_output[channel] = logical_on;
    s_channel_write_count[channel]++;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemIndicatorDevice_Set(uint8_t channel,
                                             uint8_t logical_on)
{
    return TestIndicator_Set(channel, logical_on);
}

static void ResetState(void)
{
    (void)memset(&s_calibration, 0, sizeof(s_calibration));
    (void)memset(&s_alignment, 0, sizeof(s_alignment));
    (void)memset(s_channel_output, 0, sizeof(s_channel_output));
    (void)memset(s_channel_write_count, 0, sizeof(s_channel_write_count));
    (void)memset(&s_gnss_health, 0, sizeof(s_gnss_health));
    (void)memset(&s_gnss_sample, 0, sizeof(s_gnss_sample));
    s_calibration.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
    s_calibration.state = SYSTEM_CALIBRATION_STATE_IDLE;
    s_alignment.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_lifecycle = SYSTEM_STATE_PREFLIGHT;
    s_health_ready = 0U;
    s_now_us = 0U;
    s_gnss_health_result = SYSTEM_DEVICE_UNSUPPORTED;
    s_gnss_sample_result = SYSTEM_DEVICE_NOT_READY;
    SystemIndicator_Init();
}

int main(void)
{
    ResetState();
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_IDLE, 0U, 0U, 0U,
        SYSTEM_STATE_PREFLIGHT) == SYSTEM_INDICATOR_MODE_OFF);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_COLLECTING, 0U, 0U, 0U,
        SYSTEM_STATE_PREFLIGHT) == SYSTEM_INDICATOR_MODE_BLINK_FAST);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_WAIT_FACE, 0U, 0U, 0U,
        SYSTEM_STATE_PREFLIGHT) == SYSTEM_INDICATOR_MODE_BLINK_FAST);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_READY, 1U, 0U, 0U,
        SYSTEM_STATE_PREFLIGHT) == SYSTEM_INDICATOR_MODE_BLINK_SLOW);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_READY, 1U, 1U, 0U,
        SYSTEM_STATE_READY) == SYSTEM_INDICATOR_MODE_BLINK_SLOW);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_READY, 1U, 1U, 1U,
        SYSTEM_STATE_READY) == SYSTEM_INDICATOR_MODE_ON);
    TEST_CHECK(SystemIndicator_SystemModeResolve(
        SYSTEM_CALIBRATION_STATE_IDLE, 0U, 0U, 0U,
        SYSTEM_STATE_FLIGHT) == SYSTEM_INDICATOR_MODE_ON);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_UNSUPPORTED, 0U, 0U, SYSTEM_DEVICE_NOT_READY, 0U) ==
        SYSTEM_INDICATOR_MODE_OFF);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_OK, 0U, 0U, SYSTEM_DEVICE_NOT_READY, 0U) ==
        SYSTEM_INDICATOR_MODE_OFF);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_OK, 1U, 0U, SYSTEM_DEVICE_NOT_READY, 0U) ==
        SYSTEM_INDICATOR_MODE_OFF);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_OK, 1U, 1U, SYSTEM_DEVICE_NOT_READY, 0U) ==
        SYSTEM_INDICATOR_MODE_OFF);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_OK, 1U, 1U, SYSTEM_DEVICE_OK, 0U) ==
        SYSTEM_INDICATOR_MODE_BLINK_SLOW);
    TEST_CHECK(SystemIndicator_GnssModeResolve(
        SYSTEM_DEVICE_OK, 1U, 1U, SYSTEM_DEVICE_OK, 1U) ==
        SYSTEM_INDICATOR_MODE_ON);

    s_calibration.state = SYSTEM_CALIBRATION_STATE_COLLECTING;
    s_now_us = 0U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_FAST_HALF_PERIOD_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 0U);

    s_calibration.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration.ready = 1U;
    s_alignment.ready = 0U;
    s_now_us = 0U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 0U);

    s_alignment.ready = 1U;
    s_health_ready = 1U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    TEST_CHECK(SystemIndicator_ModeSet(SYSTEM_INDICATOR_GNSS,
                                        SYSTEM_INDICATOR_MODE_ON) ==
                SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemIndicator_ModeSet(SYSTEM_INDICATOR_SAFETY,
                                        SYSTEM_INDICATOR_MODE_ON) ==
                SYSTEM_DEVICE_UNSUPPORTED);

    /* A completed six-face sample briefly overrides the base blink with a
       500 ms solid confirmation, then automatically returns to base mode. */
    ResetState();
    s_calibration.mode = SYSTEM_CALIBRATION_MODE_SIX_FACE;
    s_calibration.state = SYSTEM_CALIBRATION_STATE_WAIT_FACE;
    s_now_us = 0U;
    SystemIndicator_Process();
    s_calibration.last_face = SYSTEM_CALIBRATION_FACE_X_POSITIVE;
    s_calibration.last_face_result =
        SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE;
    s_calibration.face_event_sequence = 1U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_EVENT_CONFIRM_US - 1ULL;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_EVENT_CONFIRM_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 0U);

    /* Alignment READY uses the same non-blocking confirmation overlay. */
    ResetState();
    s_calibration.mode = SYSTEM_CALIBRATION_MODE_ONE_FACE;
    s_calibration.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration.ready = 1U;
    s_alignment.state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    s_alignment.start_sequence = 1U;
    s_now_us = 0U;
    SystemIndicator_Process();
    s_alignment.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment.ready = 1U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_EVENT_CONFIRM_US - 1ULL;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_EVENT_CONFIRM_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 0U);

    ResetState();
    s_calibration.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration.ready = 1U;
    s_alignment.state = SYSTEM_ALIGNMENT_STATE_STALE;
    s_alignment.ready = 0U;
    s_now_us = 0U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 1U);
    s_now_us = SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[0] == 0U);

    /* GNSS uses the common health/sample contract and position_usable. */
    ResetState();
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 0U);
    s_gnss_health_result = SYSTEM_DEVICE_OK;
    s_gnss_health.initialized = 1U;
    s_gnss_health.online = 1U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 0U);
    s_gnss_sample_result = SYSTEM_DEVICE_OK;
    s_gnss_sample.position_usable = 0U;
    s_now_us = 0U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 1U);
    s_now_us = SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 0U);
    s_gnss_sample.position_usable = 1U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 1U);
    s_gnss_health.online = 0U;
    SystemIndicator_Process();
    TEST_CHECK(s_channel_output[1] == 0U);

    return Test_Finish("system_indicator");
}
