#include <float.h>
#include <math.h>
#include <limits.h>
#include <stdint.h>
#include <string.h>

#include "air_protocol.h"
#include "navigation_kf.h"
#include "system_estimator_profile.h"
#include "system_gnss_if.h"
#include "system_user_config.h"
#include "test_common.h"

static void Test_PutU32Le(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8);
    data[2] = (uint8_t)(value >> 16);
    data[3] = (uint8_t)(value >> 24);
}

static void Test_AirNavigation(void)
{
    static const uint8_t expected[3][9] = {
        {0x15U, 0x22U, 0x34U, 0x12U, 7U, 0U, 1U, 2U, 31U},
        {0x16U, 0x23U, 0x34U, 0x12U, 7U, 0U, 127U, 15U, 17U},
        {0x17U, 0x24U, 0x34U, 0x12U, 7U, 0U, 9U, 12U, 0U}
    };
    AirNavigationStatusPayload status = {0x1234U, 7U, {0U, 0U, 0U}};
    uint8_t frame[AIR_NAV_CAPABILITY_LEN];
    uint8_t length = 0U;
    uint8_t index;

    for (index = 0U; index < 3U; index++)
    {
        (void)memcpy(status.tail, &expected[index][6], sizeof(status.tail));
        TEST_CHECK(Air_NavigationStatusBuild(expected[index][1],
            expected[index][0], &status, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        TEST_CHECK(length == 9U);
        TEST_CHECK(memcmp(frame, expected[index], 9U) == 0);
        TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        TEST_CHECK(Air_FrameValidate(frame, 8U) == AIR_PARSE_BAD_LEN);
    }
    TEST_CHECK(Air_NavigationStatusBuild(1U, AIR_TYPE_NAV_HEALTH,
        &status, frame, 8U, &length) == AIR_BUILD_BAD_LEN);
    TEST_CHECK(length == 0U);
    status.session = 0U;
    TEST_CHECK(Air_NavigationStatusBuild(1U, AIR_TYPE_NAV_HEALTH,
        &status, frame, sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);
    TEST_CHECK(Air_CmdTokenIsValid(AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL) != 0U);
    TEST_CHECK(Air_CmdTokenIsValid(AIR_CMD_NAV_SUBSCRIBE, 0x4E560000UL) == 0U);
    TEST_CHECK(Air_CmdTokenIsValid(AIR_CMD_NAV_SUBSCRIBE, 0x4E571234UL) == 0U);
}

static void Test_Air(void)
{
    AirCapabilityPayload capability;
    AirCapabilityPayload parsed_capability;
    AirPreflightStatusPayload preflight_status;
    AirPreflightStatusPayload parsed_preflight_status;
    AirSensorStatusPayload sensor_status;
    AirSensorStatusPayload parsed_sensor_status;
    AirPreflightStatePayload preflight;
    AirFlightStatePayload state;
    AirCompactV0ImuQuantized quantized;
    AirCmdPayload command;
    float accel_mps2[3] = {
        AIR_STANDARD_GRAVITY_MPS2,
        -16.0f * AIR_STANDARD_GRAVITY_MPS2,
        20.0f * AIR_STANDARD_GRAVITY_MPS2
    };
    float gyro_radps[3] = {0.0f, 34.906585f, -40.0f};
    uint8_t preflight_frame[AIR_PREFLIGHT_STATE_LEN];
    uint8_t frame[AIR_MAX_FRAME_LEN];
    uint8_t length = 0U;

    TEST_CHECK(AIR_FLIGHT_STATE_LEN == 50U);
    TEST_CHECK(AIR_PREFLIGHT_STATE_LEN == 26U);
    TEST_CHECK(AIR_CAPABILITY_LEN == 9U);
    TEST_CHECK(AIR_PREFLIGHT_STATUS_LEN == 9U);
    TEST_CHECK(AIR_SENSOR_STATUS_LEN == 9U);
    TEST_CHECK(AIR_STATUS_LEN == 9U);
    TEST_CHECK(AIR_CMD_LEN == 9U);
    TEST_CHECK(AIR_ACK_LEN == 9U);
    TEST_CHECK(AIR_MAX_FRAME_LEN <= 64U);
    TEST_CHECK(AIR_PROTOCOL_APPLICATION_CRC_SIZE == 0U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_FLIGHT_STATE) == 50U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_PREFLIGHT_STATE) == 26U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_CAPABILITY) == 9U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_PREFLIGHT_STATUS) == 9U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_SENSOR_STATUS) == 9U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_STATUS) == 9U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_CMD) == 9U);
    TEST_CHECK(Air_GetExpectedFrameLength(AIR_TYPE_ACK) == 9U);

    capability.air_profile_id = AIR_PROFILE_COMPACT_V0;
    capability.command_policy = AIR_COMMAND_POLICY_PREFLIGHT_ONLY;
    capability.calibration_mode_mask = AIR_CALIBRATION_MODE_MASK_ALL;
    capability.sensor_summary_flags = AIR_SENSOR_SUMMARY_MASK_ALL;
    capability.accel_full_scale_g = AIR_ACCEL_FULL_SCALE_G;
    capability.gyro_full_scale_dps = AIR_GYRO_FULL_SCALE_DPS;
    TEST_CHECK(Air_CapabilityBuild(3U, &capability, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(length == AIR_CAPABILITY_LEN);
    TEST_CHECK(frame[0] == AIR_TYPE_CAPABILITY && frame[1] == 3U);
    TEST_CHECK(frame[2] == 0U && frame[3] == 1U && frame[4] == 0x07U);
    TEST_CHECK(frame[5] == 0x0FU && frame[6] == 16U);
    TEST_CHECK(frame[7] == 0xD0U && frame[8] == 0x07U);
    TEST_CHECK(Air_CapabilityParse(frame, length, &parsed_capability) ==
               AIR_PARSE_OK);
    TEST_CHECK(parsed_capability.air_profile_id ==
               capability.air_profile_id);
    TEST_CHECK(parsed_capability.command_policy ==
               capability.command_policy);
    TEST_CHECK(parsed_capability.calibration_mode_mask ==
               capability.calibration_mode_mask);
    TEST_CHECK(parsed_capability.sensor_summary_flags ==
               capability.sensor_summary_flags);
    TEST_CHECK(parsed_capability.accel_full_scale_g ==
               capability.accel_full_scale_g);
    TEST_CHECK(parsed_capability.gyro_full_scale_dps ==
               capability.gyro_full_scale_dps);
    frame[2] = 1U;
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_BAD_FIELD);

    TEST_CHECK(Air_CompactV0ImuQuantize(accel_mps2, gyro_radps,
                                        &quantized) == AIR_BUILD_OK);
    TEST_CHECK(quantized.accel_i16[0] == 2048);
    TEST_CHECK(quantized.accel_i16[1] == INT16_MIN);
    TEST_CHECK(quantized.accel_i16[2] == INT16_MAX);
    TEST_CHECK(quantized.gyro_i16[0] == 0);
    TEST_CHECK(quantized.gyro_i16[1] == INT16_MAX);
    TEST_CHECK(quantized.gyro_i16[2] == INT16_MIN);
    TEST_CHECK(quantized.saturation_count == 3U);

    TEST_CHECK(Air_StatusBuild(7U, AIR_STATUS_GNSS_POSITION, 1234U,
                               1U, 0U, frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    TEST_CHECK(length == 9U);
    TEST_CHECK(frame[0] == AIR_TYPE_STATUS);
    TEST_CHECK(frame[2] == 0x09U);
    TEST_CHECK(frame[7] == 1U);
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
    frame[8] = 1U;
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_BAD_FIELD);

    TEST_CHECK(Air_StatusBuild(8U, AIR_STATUS_SELFTEST_COMPLETE, 1235U,
                               0U, 0U, frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    TEST_CHECK(frame[2] == 0x02U && frame[7] == 0U && frame[8] == 0U);
    TEST_CHECK(Air_StatusBuild(9U, AIR_STATUS_SELFTEST_COMPLETE, 1236U,
                               1U, 0U, frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    TEST_CHECK(frame[7] == 1U && frame[8] == 0U);
    TEST_CHECK(Air_StatusBuild(10U, AIR_STATUS_SELFTEST_COMPLETE, 1237U,
                               2U, 0U, frame, sizeof(frame), &length) ==
               AIR_BUILD_BAD_PARAM);
    TEST_CHECK(Air_StatusBuild(11U, AIR_STATUS_SELFTEST_COMPLETE, 1238U,
                               1U, 1U, frame, sizeof(frame), &length) ==
               AIR_BUILD_BAD_PARAM);

    TEST_CHECK(Air_StatusBuild(12U, AIR_STATUS_ALIGNMENT, 1239U,
                               AIR_ALIGNMENT_STATE_READY,
                               0x5AU,
                               frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    TEST_CHECK(frame[2] == 0x0AU);
    TEST_CHECK(frame[7] == AIR_ALIGNMENT_STATE_READY);
    TEST_CHECK(frame[8] == 0x5AU);
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
    TEST_CHECK(Air_StatusBuild(16U, AIR_STATUS_ALIGNMENT, 1243U,
                               AIR_ALIGNMENT_STATE_COLLECTING, 0x80U,
                               frame, sizeof(frame), &length) ==
               AIR_BUILD_BAD_PARAM);
    TEST_CHECK(Air_StatusBuild(17U, AIR_STATUS_CALIBRATION, 1244U,
                               AIR_CALIBRATION_STATE_READY,
                               AIR_CALIBRATION_MODE_NONE,
                               frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    TEST_CHECK(Air_StatusBuild(18U, AIR_STATUS_CALIBRATION_FACE, 1245U,
                               AIR_CALIBRATION_FACE_Z_NEGATIVE,
                               AIR_CALIBRATION_FACE_PASSED,
                               frame, sizeof(frame), &length) ==
               AIR_BUILD_OK);
    {
        uint8_t reason;

        for (reason = AIR_CALIBRATION_DIAGNOSTIC_NONE;
             reason <= AIR_CALIBRATION_DIAGNOSTIC_SAMPLE_GAP;
             reason++)
        {
            TEST_CHECK(Air_StatusBuild(19U,
                AIR_STATUS_CALIBRATION_DIAGNOSTIC, 1246U,
                AIR_CALIBRATION_FACE_X_POSITIVE, reason,
                frame, sizeof(frame), &length) == AIR_BUILD_OK);
            TEST_CHECK(length == AIR_STATUS_LEN);
            TEST_CHECK(frame[2] ==
                       AIR_STATUS_CALIBRATION_DIAGNOSTIC);
            TEST_CHECK(frame[7] == AIR_CALIBRATION_FACE_X_POSITIVE);
            TEST_CHECK(frame[8] == reason);
            TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
        }
    }
    TEST_CHECK(Air_StatusBuild(19U,
        AIR_STATUS_CALIBRATION_DIAGNOSTIC, 1246U,
        AIR_CALIBRATION_FACE_NOT_SELECTED,
        AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING,
        frame, sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(Air_StatusBuild(19U,
        AIR_STATUS_CALIBRATION_DIAGNOSTIC, 1246U, 6U,
        AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING,
        frame, sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);
    TEST_CHECK(Air_StatusBuild(19U,
        AIR_STATUS_CALIBRATION_DIAGNOSTIC, 1246U,
        AIR_CALIBRATION_FACE_NOT_SELECTED, 7U,
        frame, sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);
    TEST_CHECK(Air_StatusBuild(19U, AIR_STATUS_ALIGNMENT, 1246U,
        AIR_ALIGNMENT_STATE_STALE, 0xFFU,
        frame, sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
    TEST_CHECK(Air_StatusBuild(19U, AIR_STATUS_ALIGNMENT, 1246U,
        AIR_ALIGNMENT_STATE_STALE, 0U,
        frame, sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);

    (void)memset(&sensor_status, 0, sizeof(sensor_status));
    sensor_status.snapshot_id = 7U;
    sensor_status.sensor_id = SILVERSTAR_SENSOR_ID_BAROMETER;
    sensor_status.instance_id = 2U;
    sensor_status.status_flags = AIR_SENSOR_STATUS_REGISTERED |
        AIR_SENSOR_STATUS_INITIALIZED | AIR_SENSOR_STATUS_ONLINE |
        AIR_SENSOR_STATUS_HEALTHY | AIR_SENSOR_STATUS_DATA_VALID |
        AIR_SENSOR_STATUS_ALIGNMENT_USED;
    sensor_status.detail_code = 0U;
    sensor_status.index = 2U;
    sensor_status.total = 5U;
    TEST_CHECK(Air_SensorStatusBuild(21U, &sensor_status, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(length == AIR_SENSOR_STATUS_LEN);
    TEST_CHECK(frame[0] == AIR_TYPE_SENSOR_STATUS && frame[1] == 21U);
    TEST_CHECK(frame[2] == 7U && frame[3] == 0x03U && frame[4] == 2U);
    TEST_CHECK(frame[5] == sensor_status.status_flags &&
               frame[6] == 0U && frame[7] == 2U && frame[8] == 5U);
    TEST_CHECK(Air_SensorStatusParse(frame, length,
        &parsed_sensor_status) == AIR_PARSE_OK);
    TEST_CHECK(memcmp(&sensor_status, &parsed_sensor_status,
                      sizeof(sensor_status)) == 0);
    sensor_status.sensor_id = 0x80U;
    TEST_CHECK(Air_SensorStatusBuild(21U, &sensor_status, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(Air_SensorStatusParse(frame, length,
        &parsed_sensor_status) == AIR_PARSE_OK);
    TEST_CHECK(parsed_sensor_status.sensor_id == 0x80U);
    sensor_status.index = sensor_status.total;
    TEST_CHECK(Air_SensorStatusBuild(21U, &sensor_status, frame,
        sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);
    sensor_status.index = 0U;
    sensor_status.sensor_id = SILVERSTAR_SENSOR_ID_BAROMETER;
    sensor_status.detail_code = 0x0BU;
    TEST_CHECK(Air_SensorStatusBuild(21U, &sensor_status, frame,
        sizeof(frame), &length) == AIR_BUILD_BAD_PARAM);
    TEST_CHECK(SILVERSTAR_SENSOR_ID_IMU == 0x01U);
    TEST_CHECK(SILVERSTAR_SENSOR_ID_GNSS == 0x02U);
    TEST_CHECK(SILVERSTAR_SENSOR_ID_HUMIDITY == 0x0EU);
    TEST_CHECK(Air_CmdIdIsValid(0x06U) == 0U);

    (void)memset(frame, 0, sizeof(frame));
    frame[0] = AIR_TYPE_CMD;
    frame[1] = 9U;
    frame[2] = AIR_CMD_START_MISSION;
    Test_PutU32Le(&frame[3], AIR_TOKEN_START_MISSION);
    TEST_CHECK(Air_CmdParse(frame, AIR_CMD_LEN, &command) == AIR_PARSE_OK);
    TEST_CHECK(command.seq == 9U);
    TEST_CHECK(command.token == AIR_TOKEN_START_MISSION);
    TEST_CHECK(Air_CmdParse(frame, AIR_CMD_LEN - 1U, &command) ==
               AIR_PARSE_BAD_LEN);
    frame[3] ^= 1U;
    TEST_CHECK(Air_CmdParse(frame, AIR_CMD_LEN, &command) ==
               AIR_PARSE_BAD_TOKEN);

    (void)memset(frame, 0, sizeof(frame));
    frame[0] = AIR_TYPE_CMD;
    frame[1] = 10U;
    frame[2] = AIR_CMD_CAPABILITY_ACK;
    frame[7] = 3U;
    frame[8] = AIR_PROFILE_COMPACT_V0;
    TEST_CHECK(Air_CmdParse(frame, AIR_CMD_LEN, &command) == AIR_PARSE_OK);
    TEST_CHECK(command.param0 == 3U && command.param1 == 0U);

    (void)memset(&preflight_status, 0, sizeof(preflight_status));
    preflight_status.lifecycle_state = AIR_LIFECYCLE_PREFLIGHT;
    preflight_status.calibration_state = AIR_CALIBRATION_STATE_READY;
    preflight_status.calibration_mode = AIR_CALIBRATION_MODE_SIX_FACE;
    preflight_status.completed_face_mask = 0x3FU;
    preflight_status.current_face =
        AIR_CALIBRATION_FACE_NOT_SELECTED;
    preflight_status.alignment_state = AIR_ALIGNMENT_STATE_READY;
    preflight_status.flags = AIR_PREFLIGHT_FLAG_SYSTEM_READY |
        AIR_PREFLIGHT_FLAG_START_UNLOCKED |
        AIR_PREFLIGHT_FLAG_SELFTEST_PASSED |
        AIR_PREFLIGHT_FLAG_GNSS_USABLE |
        AIR_PREFLIGHT_FLAG_CAPABILITY_ACKED |
        AIR_PREFLIGHT_FLAG_CALIBRATION_READY |
        AIR_PREFLIGHT_FLAG_ALIGNMENT_READY;
    preflight_status.start_block_reason = AIR_ACK_RESULT_OK;
    TEST_CHECK(Air_PreflightStatusBuild(19U, &preflight_status, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(length == AIR_PREFLIGHT_STATUS_LEN);
    TEST_CHECK(frame[0] == AIR_TYPE_PREFLIGHT_STATUS && frame[1] == 19U);
    TEST_CHECK(frame[2] == AIR_LIFECYCLE_PREFLIGHT);
    TEST_CHECK(frame[3] == 0x24U);
    TEST_CHECK(frame[4] == 0x3FU && frame[5] == 0xFFU);
    TEST_CHECK(frame[6] == 0x03U && frame[7] == 0x7FU);
    TEST_CHECK(frame[8] == AIR_ACK_RESULT_OK);
    TEST_CHECK(Air_PreflightStatusParse(frame, length,
        &parsed_preflight_status) == AIR_PARSE_OK);
    TEST_CHECK(memcmp(&preflight_status, &parsed_preflight_status,
                      sizeof(preflight_status)) == 0);
    preflight_status.alignment_state = AIR_ALIGNMENT_STATE_STALE;
    preflight_status.flags &=
        (uint8_t)(~AIR_PREFLIGHT_FLAG_ALIGNMENT_READY);
    preflight_status.start_block_reason =
        AIR_ACK_RESULT_ALIGNMENT_REQUIRED;
    TEST_CHECK(Air_PreflightStatusBuild(20U, &preflight_status, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(Air_PreflightStatusParse(frame, length,
        &parsed_preflight_status) == AIR_PARSE_OK);
    TEST_CHECK(parsed_preflight_status.alignment_state ==
               AIR_ALIGNMENT_STATE_STALE);
    TEST_CHECK((parsed_preflight_status.flags &
                AIR_PREFLIGHT_FLAG_ALIGNMENT_READY) == 0U);
    TEST_CHECK(parsed_preflight_status.start_block_reason ==
               AIR_ACK_RESULT_ALIGNMENT_REQUIRED);
    frame[6] = 0x82U;
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_BAD_FIELD);

    TEST_CHECK(Air_AckBuild(20U, 21U, 0x55U,
        AIR_ACK_RESULT_BAD_CMD, 0x12345678UL, frame, sizeof(frame),
        &length) == AIR_BUILD_OK);
    TEST_CHECK(length == AIR_ACK_LEN && frame[2] == 21U &&
               frame[3] == 0x55U);
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);

    (void)memset(&preflight, 0, sizeof(preflight));
    preflight.time_ms = 0x12345678UL;
    (void)memcpy(preflight.accel_i16, quantized.accel_i16,
                 sizeof(preflight.accel_i16));
    (void)memcpy(preflight.gyro_i16, quantized.gyro_i16,
                 sizeof(preflight.gyro_i16));
    preflight.quaternion_q15[0] = INT16_MAX;
    TEST_CHECK(Air_PreflightStateBuild(4U, &preflight, preflight_frame,
        sizeof(preflight_frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(length == AIR_PREFLIGHT_STATE_LEN);
    TEST_CHECK(preflight_frame[0] == AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(preflight_frame[2] == 0x78U && preflight_frame[5] == 0x12U);
    TEST_CHECK(Air_FrameValidate(preflight_frame, length) == AIR_PARSE_OK);

    (void)memset(&state, 0, sizeof(state));
    state.time_ms = 0x12345678UL;
    (void)memcpy(state.accel_i16, preflight.accel_i16,
                 sizeof(state.accel_i16));
    (void)memcpy(state.gyro_i16, preflight.gyro_i16,
                 sizeof(state.gyro_i16));
    (void)memcpy(state.quaternion_q15, preflight.quaternion_q15,
                 sizeof(state.quaternion_q15));
    state.velocity_enu_mps[0] = 1.25f;
    state.position_enu_m[2] = -3.5f;
    TEST_CHECK(Air_FlightStateBuild(5U, &state, frame, sizeof(frame),
                                    &length) == AIR_BUILD_OK);
    TEST_CHECK(length == 50U);
    TEST_CHECK(frame[0] == 0x10U);
    TEST_CHECK(frame[1] == 5U);
    TEST_CHECK(frame[2] == 0x78U && frame[5] == 0x12U);
    TEST_CHECK(frame[18] == 0xFFU && frame[19] == 0x7FU);
    TEST_CHECK(memcmp(&preflight_frame[2], &frame[2], 24U) == 0);
    TEST_CHECK(Air_FrameValidate(frame, length) == AIR_PARSE_OK);
}

static void Test_CovarianceCheck(const NavigationKfContext *context)
{
    uint8_t row;
    uint8_t column;

    for (row = 0U; row < 6U; row++)
    {
        TEST_CHECK(isfinite(context->covariance[row][row]));
        TEST_CHECK(context->covariance[row][row] >= 0.0f);
        for (column = 0U; column < 6U; column++)
        {
            TEST_CHECK(isfinite(context->covariance[row][column]));
            TEST_CHECK_NEAR(context->covariance[row][column],
                            context->covariance[column][row], 1.0e-5f);
        }
    }
}

typedef struct
{
    uint32_t guard_before;
    NavigationKfContext kf;
    int32_t origin_lat_e7;
    int32_t origin_lon_e7;
    int32_t origin_height_mm;
    uint32_t guard_after;
} TestKfOriginContainer;

static void Test_GnssEpochSet(NavigationKfGnssEpoch *epoch,
                              uint64_t timestamp_us,
                              const float position_enu_m[3],
                              const float velocity_enu_mps[3])
{
    uint8_t index;

    (void)memset(epoch, 0, sizeof(*epoch));
    epoch->timestamp_us = timestamp_us;
    epoch->valid_group_mask =
        NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL) |
        NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_POSITION_VERTICAL) |
        NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL) |
        NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL);
    for (index = 0U; index < 3U; index++)
    {
        epoch->position_enu_m[index] = position_enu_m[index];
        epoch->velocity_enu_mps[index] = velocity_enu_mps[index];
        epoch->position_std_m[index] = (index == 2U) ? 1.5f : 1.0f;
        epoch->velocity_std_mps[index] = 0.2f;
    }
}

static void Test_GnssGroupResultsProcess(
    NavigationKfContext *context,
    const NavigationKfGnssSeparatedUpdateResult *position_result,
    const NavigationKfGnssSeparatedUpdateResult *velocity_result)
{
    if ((context != NULL) && (position_result != NULL) &&
        (position_result->horizontal_attempted != 0U))
    {
        NavigationKf_GnssGroupResultProcess(
            context, NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL,
            position_result->horizontal_result);
        NavigationKf_GnssGroupResultProcess(
            context, NAV_KF_GNSS_GROUP_POSITION_VERTICAL,
            position_result->vertical_result);
    }
    if ((context != NULL) && (velocity_result != NULL) &&
        (velocity_result->horizontal_attempted != 0U))
    {
        NavigationKf_GnssGroupResultProcess(
            context, NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL,
            velocity_result->horizontal_result);
        if (velocity_result->vertical_attempted != 0U)
        {
            NavigationKf_GnssGroupResultProcess(
                context, NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL,
                velocity_result->vertical_result);
        }
    }
}

static void Test_KfGnssGroupIsolation(void)
{
    NavigationKfContext context;
    NavigationKfGnssSeparatedUpdateResult separated;
    float position[3] = {0.0f, 0.0f, 1000.0f};
    float velocity[3] = {0.0f, 0.0f, 1000.0f};
    float position_variance[3] = {1.0f, 1.0f, 1.0f};
    float velocity_variance[3] = {0.1f, 0.1f, 0.1f};
    uint32_t aggregate_updates;

    NavigationKf_Init(&context);
    TEST_CHECK(NavigationKf_UpdateGnssPositionSeparated(
        &context, position, position_variance, &separated) ==
        NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_REJECTED_NIS);
    aggregate_updates = context.position_accept_count +
        context.position_soft_count + context.position_reject_count;
    TEST_CHECK(aggregate_updates == 1U);
    TEST_CHECK(context.position_accept_count == 1U);
    TEST_CHECK(context.gnss_group_accept_count[
        NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL] == 1U);
    TEST_CHECK(context.gnss_group_reject_count[
        NAV_KF_GNSS_GROUP_POSITION_VERTICAL] == 1U);

    NavigationKf_Init(&context);
    position[0] = 1000.0f;
    position[2] = 0.0f;
    TEST_CHECK(NavigationKf_UpdateGnssPositionSeparated(
        &context, position, position_variance, &separated) ==
        NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_REJECTED_NIS);
    TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_ACCEPTED);

    NavigationKf_Init(&context);
    TEST_CHECK(NavigationKf_UpdateGnssVelocitySeparated(
        &context, velocity, velocity_variance, 1U, &separated) ==
        NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_REJECTED_NIS);
    aggregate_updates = context.velocity_accept_count +
        context.velocity_soft_count + context.velocity_reject_count;
    TEST_CHECK(aggregate_updates == 1U);
    TEST_CHECK(context.gnss_group_accept_count[
        NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL] == 1U);
    TEST_CHECK(context.gnss_group_reject_count[
        NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL] == 1U);

    NavigationKf_Init(&context);
    velocity[0] = 1000.0f;
    velocity[2] = 0.0f;
    TEST_CHECK(NavigationKf_UpdateGnssVelocitySeparated(
        &context, velocity, velocity_variance, 1U, &separated) ==
        NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_REJECTED_NIS);
    TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_ACCEPTED);
}

static void Test_KfGnssMotionConsistency(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    float position[3];
    float velocity[3];
    uint32_t sample;

    NavigationKf_Init(&context);
    for (sample = 0U; sample < 8U; sample++)
    {
        float time_s = (float)sample * 0.04f;

        velocity[0] = 50.0f * time_s;
        velocity[1] = 0.0f;
        velocity[2] = 20.0f * time_s;
        position[0] = 0.5f * 50.0f * time_s * time_s;
        position[1] = 0.0f;
        position[2] = 0.5f * 20.0f * time_s * time_s;
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&context, &epoch);
    }
    TEST_CHECK(context.gnss_reacquisition.consistency_mask ==
        (NAV_KF_GNSS_GROUP_MASK(
             NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL) |
         NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_POSITION_VERTICAL) |
         NAV_KF_GNSS_GROUP_MASK(
             NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL) |
         NAV_KF_GNSS_GROUP_MASK(NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL)));
    TEST_CHECK(context.gnss_reacquisition.group[
        NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL].consistent_count >=
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT);
}

static void Test_KfGnssOutlierProtection(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult position_result;
    float position[3] = {0.0f, 0.0f, 0.0f};
    const float velocity[3] = {0.0f, 0.0f, 0.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    float horizontal_variance_before;

    NavigationKf_Init(&context);
    Test_GnssEpochSet(&epoch, 1000000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    (void)NavigationKf_UpdateGnssPositionSeparated(
        &context, position, variance, &position_result);
    Test_GnssGroupResultsProcess(&context, &position_result, NULL);
    TEST_CHECK(context.gnss_reacquisition.reacquire_count == 0U);
    horizontal_variance_before = context.covariance[0][0];

    position[0] = 1000.0f;
    Test_GnssEpochSet(&epoch, 1040000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    (void)NavigationKf_UpdateGnssPositionSeparated(
        &context, position, variance, &position_result);
    TEST_CHECK(position_result.horizontal_result ==
               NAV_KF_UPDATE_REJECTED_NIS);
    Test_GnssGroupResultsProcess(&context, &position_result, NULL);
    TEST_CHECK(context.gnss_reacquisition.active_mask == 0U);
    TEST_CHECK_NEAR(context.covariance[0][0], horizontal_variance_before,
                    1.0e-6f);

    position[0] = 0.0f;
    Test_GnssEpochSet(&epoch, 1080000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    (void)NavigationKf_UpdateGnssPositionSeparated(
        &context, position, variance, &position_result);
    TEST_CHECK(position_result.horizontal_result == NAV_KF_UPDATE_ACCEPTED);
    Test_GnssGroupResultsProcess(&context, &position_result, NULL);
    TEST_CHECK(context.gnss_reacquisition.active_mask == 0U);
}

static void Test_KfGnssJumpingDoesNotReacquire(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult position_result;
    float position[3] = {1000.0f, 0.0f, 0.0f};
    const float velocity[3] = {0.0f, 0.0f, 0.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    uint32_t sample;

    NavigationKf_Init(&context);
    for (sample = 0U; sample < 30U; sample++)
    {
        position[0] = ((sample & 1U) == 0U) ? 1000.0f : -1000.0f;
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&context, &epoch);
        (void)NavigationKf_UpdateGnssPositionSeparated(
            &context, position, variance, &position_result);
        TEST_CHECK(position_result.horizontal_result ==
                   NAV_KF_UPDATE_REJECTED_NIS);
        Test_GnssGroupResultsProcess(&context, &position_result, NULL);
    }
    TEST_CHECK(context.gnss_reacquisition.reacquire_count == 0U);
    TEST_CHECK(context.gnss_reacquisition.active_mask == 0U);
    TEST_CHECK_NEAR(context.covariance[0][0], 4.0f, 1.0e-6f);
}

static void Test_KfGnssPredictionLossRecovery(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult position_result;
    NavigationKfGnssSeparatedUpdateResult velocity_result;
    const float zero_delta_velocity[3] = {0.0f, 0.0f, 0.0f};
    const float position_variance[3] = {1.0f, 1.0f, 2.25f};
    const float velocity_variance[3] = {0.04f, 0.04f, 0.04f};
    float position[3] = {0.0f, 0.0f, 0.0f};
    float velocity[3] = {10.0f, 0.0f, 0.0f};
    uint32_t sample;
    uint8_t active_seen = 0U;
    uint8_t accepted_after_active = 0U;

    NavigationKf_Init(&context);
    context.state[0] = -30.0f;
    context.state[3] = 10.0f;
    Test_GnssEpochSet(&epoch, 500000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    for (sample = 0U; sample < 80U; sample++)
    {
        if (sample != 0U)
        {
            TEST_CHECK(NavigationKf_Predict(
                &context, zero_delta_velocity, 0.04f) != 0U);
        }
        position[0] = (float)sample * 0.4f;
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&context, &epoch);
        (void)NavigationKf_UpdateGnssPositionSeparated(
            &context, position, position_variance, &position_result);
        (void)NavigationKf_UpdateGnssVelocitySeparated(
            &context, velocity, velocity_variance, 1U, &velocity_result);
        Test_GnssGroupResultsProcess(
            &context, &position_result, &velocity_result);
        if ((context.gnss_reacquisition.active_mask &
             NAV_KF_GNSS_GROUP_MASK(
                 NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL)) != 0U)
        {
            active_seen = 1U;
        }
        if ((active_seen != 0U) &&
            (position_result.horizontal_result == NAV_KF_UPDATE_ACCEPTED))
        {
            accepted_after_active = 1U;
        }
        if ((accepted_after_active != 0U) &&
            ((context.gnss_reacquisition.active_mask &
              NAV_KF_GNSS_GROUP_MASK(
                  NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL)) == 0U))
        {
            break;
        }
    }
    TEST_CHECK(active_seen != 0U);
    TEST_CHECK(accepted_after_active != 0U);
    TEST_CHECK((context.gnss_reacquisition.active_mask &
                NAV_KF_GNSS_GROUP_MASK(
                    NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL)) == 0U);
    TEST_CHECK(context.gnss_group_accept_count[
        NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL] != 0U);
    TEST_CHECK(context.gnss_reacquisition.reacquire_count != 0U);
    Test_CovarianceCheck(&context);
}

static void Test_KfGnssVelocityPredictionLossRecovery(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult velocity_result;
    const float velocity_variance[3] = {0.04f, 0.04f, 0.04f};
    float position[3] = {0.0f, 0.0f, 0.0f};
    float velocity[3] = {10.0f, 0.0f, 0.0f};
    uint32_t sample;
    uint8_t active_seen = 0U;
    uint8_t accepted_after_active = 0U;

    NavigationKf_Init(&context);
    context.state[3] = -20.0f;
    Test_GnssEpochSet(&epoch, 500000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    for (sample = 0U; sample < 80U; sample++)
    {
        position[0] = (float)sample * 0.4f;
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&context, &epoch);
        (void)NavigationKf_UpdateGnssVelocitySeparated(
            &context, velocity, velocity_variance, 1U, &velocity_result);
        Test_GnssGroupResultsProcess(&context, NULL, &velocity_result);
        if ((context.gnss_reacquisition.active_mask &
             NAV_KF_GNSS_GROUP_MASK(
                 NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL)) != 0U)
        {
            active_seen = 1U;
        }
        if ((active_seen != 0U) &&
            (velocity_result.horizontal_result == NAV_KF_UPDATE_ACCEPTED))
        {
            accepted_after_active = 1U;
        }
        if ((accepted_after_active != 0U) &&
            ((context.gnss_reacquisition.active_mask &
              NAV_KF_GNSS_GROUP_MASK(
                  NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL)) == 0U))
        {
            break;
        }
    }
    TEST_CHECK(active_seen != 0U);
    TEST_CHECK(accepted_after_active != 0U);
    TEST_CHECK((context.gnss_reacquisition.active_mask &
                NAV_KF_GNSS_GROUP_MASK(
                    NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL)) == 0U);
    TEST_CHECK(context.gnss_group_accept_count[
        NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL] != 0U);
    Test_CovarianceCheck(&context);
}

static void Test_KfGnssInflationBounded(void)
{
    NavigationKfContext context;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult position_result;
    float position[3] = {100000.0f, 0.0f, 0.0f};
    const float velocity[3] = {0.0f, 0.0f, 0.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    float variance_after_attempt_limit = 0.0f;
    uint32_t sample;
    uint32_t previous_attempt_count = 0U;
    uint32_t previous_attempt_sample = 0U;

    NavigationKf_Init(&context);
    context.covariance[0][0] =
        0.5f * SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2;
    context.covariance[1][1] =
        0.5f * SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2;
    Test_GnssEpochSet(&epoch, 500000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&context, &epoch);
    for (sample = 0U; sample < 120U; sample++)
    {
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&context, &epoch);
        (void)NavigationKf_UpdateGnssPositionSeparated(
            &context, position, variance, &position_result);
        Test_GnssGroupResultsProcess(&context, &position_result, NULL);
        if (context.gnss_reacquisition.group[
                NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL]
                .inflation_attempt_count > previous_attempt_count)
        {
            uint32_t current_attempt_count =
                context.gnss_reacquisition.group[
                    NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL]
                    .inflation_attempt_count;

            TEST_CHECK(current_attempt_count == previous_attempt_count + 1U);
            if (previous_attempt_count != 0U)
            {
                TEST_CHECK((sample - previous_attempt_sample) >=
                    SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES);
            }
            previous_attempt_count = current_attempt_count;
            previous_attempt_sample = sample;
        }
        if (context.gnss_reacquisition.group[
                NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL]
                .inflation_attempt_count ==
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS)
        {
            if (variance_after_attempt_limit == 0.0f)
            {
                variance_after_attempt_limit = context.covariance[0][0];
            }
        }
    }
    TEST_CHECK(context.gnss_reacquisition.group[
        NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL].inflation_attempt_count ==
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS);
    TEST_CHECK(context.covariance[0][0] <=
               SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2);
    TEST_CHECK_NEAR(context.covariance[0][0],
                    variance_after_attempt_limit, 1.0e-4f);
    Test_CovarianceCheck(&context);
}

static void Test_KfGnssOriginInvariant(void)
{
    TestKfOriginContainer estimator;
    NavigationKfGnssEpoch epoch;
    NavigationKfGnssSeparatedUpdateResult position_result;
    float position[3] = {1000.0f, 0.0f, 0.0f};
    const float velocity[3] = {0.0f, 0.0f, 0.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    uint32_t sample;

    (void)memset(&estimator, 0, sizeof(estimator));
    estimator.guard_before = 0x12345678UL;
    estimator.origin_lat_e7 = 311234567;
    estimator.origin_lon_e7 = 1211234567;
    estimator.origin_height_mm = 12345;
    estimator.guard_after = 0x87654321UL;
    NavigationKf_Init(&estimator.kf);
    Test_GnssEpochSet(&epoch, 500000ULL, position, velocity);
    NavigationKf_GnssEpochTrack(&estimator.kf, &epoch);
    for (sample = 0U; sample < 30U; sample++)
    {
        Test_GnssEpochSet(&epoch, 1000000ULL +
            ((uint64_t)sample * 40000ULL), position, velocity);
        NavigationKf_GnssEpochTrack(&estimator.kf, &epoch);
        (void)NavigationKf_UpdateGnssPositionSeparated(
            &estimator.kf, position, variance, &position_result);
        Test_GnssGroupResultsProcess(
            &estimator.kf, &position_result, NULL);
    }
    TEST_CHECK(estimator.kf.gnss_reacquisition.reacquire_count != 0U);
    TEST_CHECK(estimator.guard_before == 0x12345678UL);
    TEST_CHECK(estimator.origin_lat_e7 == 311234567);
    TEST_CHECK(estimator.origin_lon_e7 == 1211234567);
    TEST_CHECK(estimator.origin_height_mm == 12345);
    TEST_CHECK(estimator.guard_after == 0x87654321UL);
}

static void Test_Kf(void)
{
    NavigationKfContext context;
    NavigationKfContext context_3d;
    NavigationKfContext normal;
    NavigationKfContext soft;
    NavigationKfContext backup;
    NavigationKfGnssSeparatedUpdateResult separated;
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    float p0[6][6];
    float position_std[3] = {2.0f, 2.0f, 3.0f};
    float velocity_std[3] = {0.2f, 0.2f, 99.0f};
    float velocity_2d[2] = {0.2f, 0.2f};
    float variance_2d[2] = {0.1f, 0.1f};
    float velocity_3d[3] = {0.0f, 0.0f, 1.0f};
    float variance_3d[3] = {0.1f, 0.1f, 0.1f};
    float threshold_probe_2d[2] = {4.330127f, 0.0f};
    float threshold_probe_3d[3] = {4.330127f, 0.0f, 0.0f};
    float unit_variance_2d[2] = {1.0f, 1.0f};
    float unit_variance_3d[3] = {1.0f, 1.0f, 1.0f};
    float shared_measurement[2] = {2.0f, 0.0f};
    float normal_soft[3] = {100.0f, 100.0f, 100.0f};
    float weighted_soft[3] = {0.1f, 0.1f, 0.1f};
    float common_hard[3] = {200.0f, 200.0f, 200.0f};
    NavigationKfUpdateResult result;

    NavigationKf_Init(&context);
    TEST_CHECK_NEAR(context.process_accel_std_mps2[0], 1.5f, 1.0e-6f);
    TEST_CHECK_NEAR(context.process_accel_std_mps2[2], 2.0f, 1.0e-6f);
    TEST_CHECK_NEAR(context.baro_std_m, SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_VALUE, 1.0e-6f);
    TEST_CHECK_NEAR(context.nis_soft_threshold[1], 9.210f, 1.0e-4f);
    TEST_CHECK_NEAR(context.nis_hard_threshold[2], 16.266f, 1.0e-4f);
    TEST_CHECK_NEAR(profile->p0_diagonal[5], 0.25f, 1.0e-6f);
    TEST_CHECK_NEAR(profile->process_accel_std_mps2[2], 2.0f, 1.0e-6f);
    TEST_CHECK_NEAR(profile->gnss_accuracy_scale, 1.25f, 1.0e-6f);
    TEST_CHECK_NEAR(profile->barometer_altitude_std_m, SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_VALUE, 1.0e-6f);

    SystemEstimatorProfile_BuildP0(p0, position_std, velocity_std,
        SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N);
    TEST_CHECK_NEAR(p0[5][5], 0.25f, 1.0e-6f);
    TEST_CHECK(p0[3][3] >= (0.25f * 0.25f));

    context.state[5] = 5.0f;
    result = NavigationKf_UpdateGnssVelocity2D(
        &context, velocity_2d, variance_2d);
    TEST_CHECK(result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK_NEAR(context.state[5], 5.0f, 1.0e-6f);

    NavigationKf_Init(&context_3d);
    result = NavigationKf_UpdateGnssVelocity3D(
        &context_3d, velocity_3d, variance_3d);
    TEST_CHECK(result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(context_3d.state[5] > 0.0f);

    NavigationKf_Init(&context);
    backup = context;
    result = NavigationKf_UpdateGnssVelocity2D(
        &context, threshold_probe_2d, unit_variance_2d);
    TEST_CHECK(result == NAV_KF_UPDATE_REJECTED_NIS);
    TEST_CHECK(memcmp(context.state, backup.state, sizeof(context.state)) == 0);
    TEST_CHECK(memcmp(context.covariance, backup.covariance,
                      sizeof(context.covariance)) == 0);

    NavigationKf_Init(&context_3d);
    result = NavigationKf_UpdateGnssVelocitySeparated(
        &context_3d, threshold_probe_3d, unit_variance_3d, 1U,
        &separated);
    TEST_CHECK(result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_REJECTED_NIS);
    TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_ACCEPTED);

    NavigationKf_Init(&normal);
    NavigationKf_Init(&soft);
    NavigationKf_SetNisThresholds(&normal, normal_soft, common_hard, 10.0f);
    NavigationKf_SetNisThresholds(&soft, weighted_soft, common_hard, 10.0f);
    TEST_CHECK(NavigationKf_UpdateGnssVelocity2D(
        &normal, shared_measurement, unit_variance_2d) ==
        NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(NavigationKf_UpdateGnssVelocity2D(
        &soft, shared_measurement, unit_variance_2d) ==
        NAV_KF_UPDATE_SOFT_WEIGHTED);
    TEST_CHECK(fabsf(soft.state[3]) < fabsf(normal.state[3]));
    Test_CovarianceCheck(&soft);

    NavigationKf_Init(&context);
    {
        float pz_before = context.covariance[2][2];

        result = NavigationKf_UpdateBaroAltitude(&context, 0.25f, 25.0f);
        TEST_CHECK(result == NAV_KF_UPDATE_ACCEPTED);
        TEST_CHECK(context.baro_accept_count == 1U);
        TEST_CHECK(context.covariance[2][2] < pz_before);
    }

    NavigationKf_Init(&context);
    backup = context;
    result = NavigationKf_UpdateBaroAltitude(&context, 1000.0f, 25.0f);
    TEST_CHECK(result == NAV_KF_UPDATE_REJECTED_NIS);
    TEST_CHECK(context.baro_reject_count == 1U);
    TEST_CHECK(memcmp(context.state, backup.state, sizeof(context.state)) == 0);

    NavigationKf_Init(&context);
    {
        const float delta_velocity_enu_mps[3] = {0.0f, 0.0f, 0.0f};
        const float position_enu_m[3] = {0.0f, 0.0f, 0.0f};
        const float position_variance_m2[3] = {4.0f, 4.0f, 9.0f};
        uint32_t position_updates;
        uint32_t baro_updates;

        TEST_CHECK(NavigationKf_Predict(
            &context, delta_velocity_enu_mps, 0.005f) != 0U);
        TEST_CHECK(NavigationKf_UpdateBaroAltitude(
            &context, 0.0f, 25.0f) == NAV_KF_UPDATE_ACCEPTED);
        TEST_CHECK(NavigationKf_UpdateGnssPosition(
            &context, position_enu_m, position_variance_m2) ==
            NAV_KF_UPDATE_ACCEPTED);
        position_updates = context.position_accept_count +
            context.position_soft_count + context.position_reject_count;
        baro_updates = context.baro_accept_count +
            context.baro_soft_count + context.baro_reject_count;
        TEST_CHECK(context.predict_count == 1U);
        TEST_CHECK(position_updates == 1U);
        TEST_CHECK(baro_updates == 1U);
        TEST_CHECK((position_updates + baro_updates) == 2U);
    }
}

static void Test_KfZeroGainCannotFuse(void)
{
    NavigationKfContext context, before;
    float covariance[6][6] = {{0.0f}};
    const float observation[3] = {1.0f, 1.0f, 1.0f};
    const float variance[3] = {FLT_MAX, FLT_MAX, FLT_MAX};
    uint8_t axis;
    NavigationKf_Init(&context);
    for (axis = 0U; axis < 6U; axis++)
    { covariance[axis][axis] = SYSTEM_ESTIMATOR_P_DIAGONAL_MIN; }
    TEST_CHECK(NavigationKf_ResetWithCovariance(&context, &covariance[0][0]) != 0U);
    before = context;
    TEST_CHECK(NavigationKf_UpdateGnssPosition(&context, observation, variance) == NAV_KF_UPDATE_NUMERIC_ERROR);
    TEST_CHECK(NavigationKf_UpdateGnssVelocity3D(&context, observation, variance) == NAV_KF_UPDATE_NUMERIC_ERROR);
    TEST_CHECK(NavigationKf_UpdateBaroAltitude(&context, 1.0f, FLT_MAX) == NAV_KF_UPDATE_NUMERIC_ERROR);
    TEST_CHECK(memcmp(context.state, before.state, sizeof(context.state)) == 0);
    TEST_CHECK(memcmp(context.covariance, before.covariance, sizeof(context.covariance)) == 0);
    TEST_CHECK(context.position_accept_count == 0U && context.position_soft_count == 0U);
    TEST_CHECK(context.velocity_accept_count == 0U && context.velocity_soft_count == 0U);
    TEST_CHECK(context.baro_accept_count == 0U && context.baro_soft_count == 0U);
    TEST_CHECK(context.position_reject_count == 1U && context.velocity_reject_count == 1U && context.baro_reject_count == 1U);
    TEST_CHECK(context.numeric_error_count == 5U);
    TEST_CHECK((context.health_flags & NAV_KF_HEALTH_NUMERIC_ERROR) != 0U);
    for (axis = 0U; axis < NAV_KF_GNSS_GROUP_COUNT; axis++)
    {
        TEST_CHECK(context.gnss_group_accept_count[axis] == 0U);
        TEST_CHECK(context.gnss_group_reject_count[axis] == 1U);
    }
}

static void Test_KfFinitePositiveGainRemainsEffective(void)
{
    NavigationKfContext context;
    NavigationKfGnssSeparatedUpdateResult result;
    float covariance[6][6] = {{0.0f}};
    const float observation[3] = {1.0f, 1.0f, 1.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    uint8_t axis;
    NavigationKf_Init(&context);
    for (axis = 0U; axis < 6U; axis++)
    { covariance[axis][axis] = SYSTEM_ESTIMATOR_P_DIAGONAL_MIN; }
    TEST_CHECK(NavigationKf_ResetWithCovariance(&context, &covariance[0][0]) != 0U);
    TEST_CHECK(NavigationKf_UpdateGnssPositionGroups(&context, observation, variance, 1U, &result) == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(result.horizontal_result == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(context.state[0] > 0.0f && context.state[1] > 0.0f);
    TEST_CHECK(context.gnss_group_accept_count[0] == 1U);
    TEST_CHECK(context.numeric_error_count == 0U);
    /* Zero innovation with a normal positive gain is still a real P update. */
    NavigationKf_Init(&context);
    TEST_CHECK(NavigationKf_UpdateBaroAltitude(&context, 0.0f, 1.0f) == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(context.state[2] == 0.0f);
    TEST_CHECK(context.covariance[2][2] < SYSTEM_ESTIMATOR_P0_POSITION_U_VARIANCE_M2);
    TEST_CHECK(context.baro_accept_count == 1U);
}

static void Test_KfNonfiniteGainPreservesState(void)
{
    NavigationKfContext context, before;
    NavigationKfGnssSeparatedUpdateResult result;
    const float observation[3] = {0.0f, 0.0f, 0.0f};
    const float variance[3] = {1.0e-8f, 1.0e-8f, 1.0e-8f};
    NavigationKf_Init(&context);
    context.covariance[0][0] = SYSTEM_ESTIMATOR_P_DIAGONAL_MIN;
    /* Fault injection: finite corrupt cross covariance overflows K, not S. */
    context.covariance[3][0] = FLT_MAX;
    before = context;
    TEST_CHECK(NavigationKf_UpdateGnssPositionGroups(&context, observation, variance, 1U, &result) == NAV_KF_UPDATE_NUMERIC_ERROR);
    TEST_CHECK(result.horizontal_result == NAV_KF_UPDATE_NUMERIC_ERROR);
    TEST_CHECK(memcmp(context.state, before.state, sizeof(context.state)) == 0);
    TEST_CHECK(memcmp(context.covariance, before.covariance, sizeof(context.covariance)) == 0);
    TEST_CHECK(context.gnss_group_accept_count[0] == 0U);
    TEST_CHECK(context.gnss_group_reject_count[0] == 1U);
    TEST_CHECK(context.numeric_error_count == 1U);
    TEST_CHECK((context.health_flags & NAV_KF_HEALTH_NUMERIC_ERROR) != 0U);
}

int main(void)
{
    Test_Air();
    Test_AirNavigation();
    Test_Kf();
    Test_KfZeroGainCannotFuse();
    Test_KfFinitePositiveGainRemainsEffective();
    Test_KfNonfiniteGainPreservesState();
    Test_KfGnssGroupIsolation();
    Test_KfGnssMotionConsistency();
    Test_KfGnssOutlierProtection();
    Test_KfGnssJumpingDoesNotReacquire();
    Test_KfGnssPredictionLossRecovery();
    Test_KfGnssVelocityPredictionLossRecovery();
    Test_KfGnssInflationBounded();
    Test_KfGnssOriginInvariant();
    return Test_Finish("air_kf");
}
